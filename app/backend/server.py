"""
FastAPI backend — thin wrapper around the existing migration CLI modules.

Start:  cd app/backend && python server.py
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import secrets
import base64
import shutil
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path
from contextlib import redirect_stdout, redirect_stderr
from io import StringIO

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import uvicorn

from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def verify_password(plain, hashed):
    return pwd_context.verify(plain, hashed)

def hash_password(password):
    return pwd_context.hash(password)

# ── Ensure project root is importable ──────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.utils import load_config, setup_logging, ensure_dirs, ROOT_DIR, generate_run_id
from src.connectors.registry import get_source, get_target

setup_logging()
log = logging.getLogger(__name__)

app = FastAPI(title="DB Migration API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
from fastapi.responses import JSONResponse

SESSION_COOKIE = "db_migrator_session"

@app.middleware("http")
async def session_middleware(request: Request, call_next):
    if request.url.path.startswith("/api") and request.url.path not in ["/api/login"]:
        session = request.cookies.get(SESSION_COOKIE)
        if not session:
            return JSONResponse(status_code=401, content={"detail": "Not authenticated"})
    return await call_next(request)

# ── Helpers ────────────────────────────────────────────────────────────────

def _config(payload: ConfigPayload | None = None) -> dict:
    cfg = load_config()
    if payload:
        # Override source
        if payload.sourceEngine:
            cfg["source"]["engine"] = payload.sourceEngine
        engine = cfg["source"]["engine"]
        if engine not in cfg["source"]:
            cfg["source"][engine] = {}
        if payload.sourceHost: cfg["source"][engine]["host"] = payload.sourceHost
        if payload.sourcePort: cfg["source"][engine]["port"] = payload.sourcePort
        if payload.sourceDb: 
            cfg["source"]["database"] = payload.sourceDb
            cfg["source"][engine]["database"] = payload.sourceDb
        if payload.sourceUser: cfg["source"][engine]["user"] = payload.sourceUser
        if payload.sourcePass: cfg["source"][engine]["password"] = payload.sourcePass
        
        # Override target
        if payload.targetEngine:
            cfg["target"]["engine"] = payload.targetEngine
        engine = cfg["target"]["engine"]
        if engine not in cfg["target"]:
            cfg["target"][engine] = {}
        if payload.targetHost: cfg["target"][engine]["host"] = payload.targetHost
        if payload.targetPort: cfg["target"][engine]["port"] = payload.targetPort
        if payload.targetDb: 
            cfg["target"]["schema"] = payload.targetDb
            cfg["target"][engine]["database"] = payload.targetDb
        if payload.targetUser: cfg["target"][engine]["user"] = payload.targetUser
        if payload.targetPass: cfg["target"][engine]["password"] = payload.targetPass

        # LLM
        if payload.llmProvider: cfg.setdefault("llm", {})["provider"] = payload.llmProvider
        if payload.azureDeployment: cfg.setdefault("llm", {})["azure_deployment"] = payload.azureDeployment
        if payload.azureEndpoint: cfg.setdefault("llm", {})["azure_endpoint"] = payload.azureEndpoint

        # Migration
        if payload.chunkSize and payload.chunkSize.isdigit(): 
            cfg.setdefault("migration", {})["chunk_size"] = int(payload.chunkSize)
        cfg.setdefault("migration", {})["disable_fk_during_load"] = payload.disableFk

    return cfg


def _set_active_run_id(run_id: str) -> None:
    """Persist the currently active run ID for the web UI pipeline."""
    RUN_STATE_FILE.write_text(
        json.dumps(
            {
                "run_id": run_id,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        ),
        encoding="utf-8",
    )


def _get_active_run_id(required: bool = True) -> str | None:
    """Return the current run ID (set by /api/extract).

    If *required* is True and no run is active, raise HTTPException so the
    caller can tell the user to run extraction first.
    """
    if RUN_STATE_FILE.exists():
        try:
            data = json.loads(RUN_STATE_FILE.read_text(encoding="utf-8"))
            rid = data.get("run_id")
            if rid:
                return rid
        except Exception:
            log.warning("Failed to read run_state.json; ignoring.")
    if required:
        raise HTTPException(400, "No active run. Run extraction first.")
    return None


RUN_STATE_FILE = ROOT_DIR / "run_state.json"


def _sse(data: dict) -> str:
    return f"data: {json.dumps(data)}\n\n"


# ── Models ─────────────────────────────────────────────────────────────────

class ConfigPayload(BaseModel):
    sourceEngine: str = "postgres"
    sourceHost: str = ""
    sourcePort: str = "5432"
    sourceDb: str = ""
    sourceUser: str = ""
    sourcePass: str = ""
    targetEngine: str = "mysql"
    targetHost: str = ""
    targetPort: str = "3306"
    targetDb: str = ""
    targetUser: str = ""
    targetPass: str = ""
    llmProvider: str = "azure_openai"
    azureDeployment: str = ""
    azureEndpoint: str = ""
    chunkSize: str = "5000"
    disableFk: bool = True


from pydantic import BaseModel
import psycopg2

class LoginRequest(BaseModel):
    username: str
    password: str

# ── Routes: Authentication ───────────────────────────────────────────────
@app.post("/api/login")
def login(req: LoginRequest):
    try:
        conn = psycopg2.connect(
            host="pg-b970e07-exavalu-5c0c.l.aivencloud.com",
            database="Bi_doctor_db",
            user="avnadmin",
            password=os.getenv("DB_PASSWORD"),
            port=20301,
            sslmode="require"
        )
        cur = conn.cursor()
        cur.execute("SELECT id, password_hash FROM app_users WHERE username=%s AND is_active=TRUE", (req.username,))
        user = cur.fetchone()
        cur.close()
        conn.close()

        if not user:
            raise HTTPException(status_code=401, detail="Invalid credentials")

        user_id, password_hash = user

        if not verify_password(req.password, password_hash):
            raise HTTPException(status_code=401, detail="Invalid credentials")

        response = JSONResponse({"status": "success"})
        response.set_cookie(
            key=SESSION_COOKIE,
            value=str(user_id),
            httponly=True,
            secure=False,  # True in production HTTPS
            samesite="lax",
            max_age=60 * 60 * 4
        )
        return response

    except Exception as e:
        import traceback
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail="Internal Server Error")
    
# --- Logout route to clear the session cookie    
@app.post("/api/logout")
def logout():
    response = JSONResponse({"status": "logged_out"})
    response.delete_cookie(SESSION_COOKIE)
    return response

@app.get("/api/me")
def get_me(request: Request):
    user_id = request.cookies.get(SESSION_COOKIE)
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")

    return {"user_id": user_id}
# ── Routes: Config ─────────────────────────────────────────────────────────

@app.get("/api/config")
def get_config():
    try:
        cfg = _config()
        return cfg
    except Exception as e:
        raise HTTPException(500, str(e))

@app.post("/api/test-connection/{side}")
async def test_connection(side: str, payload: ConfigPayload):
    try:
        cfg = _config(payload)
        import asyncio
        if side == "source":
            conn = get_source(cfg["source"]["engine"])
            await asyncio.to_thread(conn.connect, cfg["source"])
            await asyncio.to_thread(conn.close)
        elif side == "target":
            conn = get_target(cfg["target"]["engine"])
            await asyncio.to_thread(conn.connect, cfg["target"])
            await asyncio.to_thread(conn.close)
        else:
            raise HTTPException(400, "Invalid side")
        return {"status": "success", "message": f"Successfully connected to {side} database"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


# ── Routes: Tables & Mappings ──────────────────────────────────────────────

@app.get("/api/tables")
def list_tables():
    """List all draft and approved table mappings."""
    tables = []
    run_id = _get_active_run_id(required=False)
    if not run_id:
        return {"tables": []}

    for status_dir in ["draft", "approved"]:
        d = ROOT_DIR / "mappings" / run_id / status_dir
        if not d.exists():
            continue
        for f in sorted(d.glob("*.json")):
            mapping = json.loads(f.read_text(encoding="utf-8"))
            tables.append({
                "name": f.stem,
                "status": status_dir,
                "columns": len(mapping.get("columns", [])),
                "source_table": mapping.get("source_table", ""),
                "target_table": mapping.get("target_table", ""),
                "warnings": 0,
            })
    return {"tables": tables}


@app.get("/api/mapping/{table}")
def get_mapping(table: str):
    """Get column mapping for a table (check approved first, then draft)."""
    run_id = _get_active_run_id(required=True)
    for status_dir in ["approved", "draft"]:
        f = ROOT_DIR / "mappings" / run_id / status_dir / f"{table}.json"
        if f.exists():
            mapping = json.loads(f.read_text(encoding="utf-8"))
            return {"status": status_dir, "mapping": mapping}
    raise HTTPException(404, f"Mapping not found for table {table} in run {run_id}")


@app.put("/api/mapping/{table}")
async def save_mapping(table: str, request: Request):
    """Save user edits to the draft mapping JSON."""
    run_id = _get_active_run_id(required=True)
    body = await request.json()

    # Write edits back to draft (or approved if already approved)
    for status_dir in ["draft", "approved"]:
        f = ROOT_DIR / "mappings" / run_id / status_dir / f"{table}.json"
        if f.exists():
            f.write_text(json.dumps(body, indent=2, ensure_ascii=False), encoding="utf-8")
            return {"status": "saved", "table": table, "location": status_dir}

    # If neither exists, create in draft
    draft_path = ROOT_DIR / "mappings" / run_id / "draft" / f"{table}.json"
    draft_path.parent.mkdir(parents=True, exist_ok=True)
    draft_path.write_text(json.dumps(body, indent=2, ensure_ascii=False), encoding="utf-8")
    return {"status": "saved", "table": table, "location": "draft"}


@app.post("/api/approve/{table}")
def approve_table(table: str):
    """Move a table mapping from draft to approved."""
    run_id = _get_active_run_id(required=True)
    src = ROOT_DIR / "mappings" / run_id / "draft" / f"{table}.json"
    dst = ROOT_DIR / "mappings" / run_id / "approved" / f"{table}.json"
    
    if not src.exists():
        raise HTTPException(404, f"Draft mapping not found for table {table} in run {run_id}")
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(src), str(dst))
    return {"status": "approved", "table": table}


@app.post("/api/approve-all")
def approve_all():
    """Move all draft mappings to approved."""
    run_id = _get_active_run_id(required=True)
    draft_dir = ROOT_DIR / "mappings" / run_id / "draft"
    approved_dir = ROOT_DIR / "mappings" / run_id / "approved"
    approved_dir.mkdir(parents=True, exist_ok=True)
    count = 0
    if draft_dir.exists():
        for f in draft_dir.glob("*.json"):
            shutil.move(str(f), str(approved_dir / f.name))
            count += 1
    # Also copy views, routines, triggers
    for category in ["views", "routines", "triggers"]:
        draft_cat = ROOT_DIR / "mappings" / run_id / "draft" / category
        if draft_cat.exists():
            approved_cat = ROOT_DIR / "mappings" / run_id / "approved" / category
            approved_cat.mkdir(parents=True, exist_ok=True)
            for f in draft_cat.glob("*.sql"):
                shutil.move(str(f), str(approved_cat / f.name))
                count += 1
    return {"approved": count}


@app.get("/api/views")
def list_views():
    """List view SQL files from approved/views."""
    views = []
    run_id = _get_active_run_id(required=False)
    if not run_id:
        return {"views": []}
        
    for status_dir in ["draft", "approved"]:
        for category in ["views", "routines", "triggers"]:
            d = ROOT_DIR / "mappings" / run_id / status_dir / category
            if not d.exists():
                continue
            for f in sorted(d.glob("*.sql")):
                views.append({"name": f.stem, "status": status_dir, "category": category, "file": f.name})
    return {"views": views}


# ── Routes: Extract (SSE) ──────────────────────────────────────────────────

@app.post("/api/extract")
async def run_extract(payload: ConfigPayload = None):
    import threading, queue
    q = queue.Queue()

    def worker():
        try:
            cfg = _config(payload)
            run_id = generate_run_id()
            _set_active_run_id(run_id)
            q.put({"type": "log", "msg": f"Run ID: {run_id}"})

            source = get_source(cfg["source"]["engine"])
            source.connect(cfg["source"])
            q.put({"type": "log", "msg": f"Connected to {cfg['source']['engine']}"})

            from src.extractor import extract_schema, extract_stats
            q.put({"type": "log", "msg": "Extracting schema..."})
            
            def progress(msg, done, total):
                q.put({"type": "progress", "msg": msg, "done": done, "total": total})

            spec_path = extract_schema(source, cfg, run_id=run_id, on_progress=progress)
            q.put({"type": "log", "msg": f"Schema extracted → {spec_path.name}"})

            q.put({"type": "log", "msg": "Collecting column statistics..."})
            extract_stats(source, cfg, spec_path, run_id=run_id)
            q.put({"type": "log", "msg": "Statistics collected"})

            # Count tables
            spec = json.loads(spec_path.read_text(encoding="utf-8"))
            n_tables = len(spec.get("tables", []))
            n_cols = sum(len(t.get("columns", [])) for t in spec.get("tables", []))
            q.put({"type": "log", "msg": f"✓ Extraction complete — {n_tables} tables, {n_cols} columns"})
            q.put({"type": "done", "tables": n_tables, "columns": n_cols, "run_id": run_id})
            source.close()
        except Exception as e:
            q.put({"type": "error", "msg": str(e)})
        finally:
            q.put(None)

    threading.Thread(target=worker, daemon=True).start()

    async def stream():
        yield _sse({"type": "log", "msg": "Connecting to source database..."})
        while True:
            item = await asyncio.to_thread(q.get)
            if item is None:
                break
            yield _sse(item)

    return StreamingResponse(stream(), media_type="text/event-stream")


# ── Routes: Propose (SSE) ─────────────────────────────────────────────────

@app.post("/api/propose")
async def run_propose(payload: ConfigPayload = None):
    import threading, queue, concurrent.futures
    q = queue.Queue()

    def worker():
        try:
            cfg = _config(payload)
            run_id = _get_active_run_id()
            from src.llm_client import build_llm, generate_mapping, translate_sql

            ensure_dirs()
            spec_dir = ROOT_DIR / "schemas" / run_id
            spec_files = list(spec_dir.glob("*.json"))
            if not spec_files:
                q.put({"type": "error", "msg": "No schema specs found. Run extract first."})
                return

            llm = build_llm(cfg)
            target_engine = cfg["target"]["engine"]
            target_schema = cfg["target"].get("schema", "public")

            # Run-scoped mapping roots
            draft_root = ROOT_DIR / "mappings" / run_id / "draft"
            approved_root = ROOT_DIR / "mappings" / run_id / "approved"
            draft_root.mkdir(parents=True, exist_ok=True)
            approved_root.mkdir(parents=True, exist_ok=True)

            tasks = []
            for spec_path in spec_files:
                spec = json.loads(spec_path.read_text(encoding="utf-8"))
                source_engine = spec["source_engine"]
                for table in spec["tables"]:
                    tasks.append((source_engine, table))

            total = len(tasks)
            done = 0

            def process_table(se, tbl):
                name = f"{tbl['schema']}.{tbl['name']}"
                q.put({"type": "log", "msg": f"Proposing mapping for {name}..."})
                mapping = generate_mapping(llm, se, target_engine, target_schema, tbl)
                mapping["source_engine"] = se
                mapping["target_engine"] = target_engine
                mapping["status"] = "draft"
                out = draft_root / f"{tbl['name']}.json"
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_text(json.dumps(mapping, indent=2, default=str), encoding="utf-8")
                return tbl["name"], len(mapping.get("columns", []))

            # Execute LLM API calls concurrently (up to 5 parallel threads)
            with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
                futures = {executor.submit(process_table, se, t): t["name"] for se, t in tasks}
                for future in concurrent.futures.as_completed(futures):
                    tname = futures[future]
                    try:
                        _, ncols = future.result()
                        done += 1
                        q.put({"type": "progress", "done": done, "total": total, "current": tname})
                        q.put({"type": "log", "msg": f"✓ {tname} — {ncols} columns"})
                    except Exception as e:
                        q.put({"type": "error", "msg": f"Failed on {tname}: {str(e)}"})
                        # Still count as done to advance progress slightly, but it failed
                        done += 1
                        q.put({"type": "progress", "done": done, "total": total, "current": tname})

            # Translate views sequentially
            for category in ["views", "routines", "triggers"]:
                src_dir = spec_dir / category
                if not src_dir.exists():
                    continue

                draft_dir = draft_root / category
                draft_dir.mkdir(parents=True, exist_ok=True)
                ObjectTypeMap = {"views": "VIEW", "routines": "PROCEDURE/FUNCTION", "triggers": "TRIGGER"}
                for sql_file in src_dir.glob("*.sql"):
                    q.put({"type": "log", "msg": f"Translating {category[:-1]}: {sql_file.name}..."})
                    sql_code = sql_file.read_text(encoding="utf-8")
                    translated = translate_sql(
                        llm, cfg["source"]["engine"], cfg["target"]["engine"],
                        sql_code, ObjectTypeMap.get(category, "SQL"),
                        object_name=sql_file.stem.split(".")[-1]
                    )
                    tgt_file = draft_dir / sql_file.name
                    tgt_file.write_text(translated, encoding="utf-8")
                    q.put({"type": "log", "msg": f"✓ {sql_file.name} translated"})

            q.put({"type": "done", "tables": done})
        except Exception as e:
            q.put({"type": "error", "msg": str(e)})
        finally:
            q.put(None)

    threading.Thread(target=worker, daemon=True).start()

    async def stream():
        while True:
            item = await asyncio.to_thread(q.get)
            if item is None:
                break
            yield _sse(item)

    return StreamingResponse(stream(), media_type="text/event-stream")


# ── Routes: Apply Schema (SSE) ────────────────────────────────────────────

@app.post("/api/apply-schema")
async def run_apply_schema(payload: ConfigPayload = None):
    async def stream():
        try:
            cfg = _config(payload)
            run_id = _get_active_run_id()
            from src.schema_gen import generate_ddl, apply_schema

            import asyncio
            target = get_target(cfg["target"]["engine"])
            await asyncio.to_thread(target.connect, cfg["target"])
            yield _sse({"type": "log", "msg": f"Connected to target {cfg['target']['engine']}"})

            ddl_paths = await asyncio.to_thread(generate_ddl, target, cfg, run_id=run_id)
            yield _sse({"type": "log", "msg": f"Generated DDL for {len(ddl_paths)} tables"})

            await asyncio.to_thread(apply_schema, target, cfg, dry_run=False, run_id=run_id)
            yield _sse({"type": "log", "msg": f"✓ Schema applied ({len(ddl_paths)} tables)"})
            yield _sse({"type": "done", "tables": len(ddl_paths), "run_id": run_id})
            target.close()
        except Exception as e:
            yield _sse({"type": "error", "msg": str(e)})

    return StreamingResponse(stream(), media_type="text/event-stream")


# ── Routes: Migrate (SSE) ─────────────────────────────────────────────────

@app.post("/api/migrate")
async def run_migrate(payload: ConfigPayload = None):
    async def stream():
        try:
            cfg = _config(payload)
            import asyncio
            from src.migrator import migrate_table

            source = get_source(cfg["source"]["engine"])
            target = get_target(cfg["target"]["engine"])
            await asyncio.to_thread(source.connect, cfg["source"])
            await asyncio.to_thread(target.connect, cfg["target"])
            yield _sse({"type": "log", "msg": "Connected to source and target"})

            run_id = _get_active_run_id()
            yield _sse({"type": "log", "msg": f"Migration run: {run_id}"})

            results = []
            approved_dir = ROOT_DIR / "mappings" / run_id / "approved"
            if approved_dir.exists():
                for mf in sorted(approved_dir.glob("*.json")):
                    mapping = json.loads(mf.read_text(encoding="utf-8"))
                    try:
                        r = await asyncio.to_thread(migrate_table, source, target, cfg, mapping, run_id)
                        results.append(r)
                        yield _sse({
                            "type": "table_done",
                            "table": r["table"],
                            "rows": r["rows_loaded"],
                            "failures": r["failures"],
                        })
                        yield _sse({"type": "log", "msg": f"✓ {r['table']} — {r['rows_loaded']:,} rows"})
                    except Exception as e:
                        tname = mapping.get("target_table", mapping.get("source_table", "Unknown"))
                        r = {"table": tname, "rows_loaded": 0, "failures": 1}
                        results.append(r)
                        yield _sse({
                            "type": "table_done",
                            "table": tname,
                            "rows": 0, 
                            "failures": 1
                        })
                        yield _sse({"type": "log", "msg": f"✗ Migrating {tname} failed: {str(e)}"})

            total = sum(r["rows_loaded"] for r in results)
            yield _sse({"type": "log", "msg": f"✓ Migration complete. {total:,} total rows."})
            yield _sse({"type": "done", "total_rows": total, "tables": len(results), "run_id": run_id})
            source.close()
            target.close()
        except Exception as e:
            yield _sse({"type": "error", "msg": traceback.format_exc()})

    return StreamingResponse(stream(), media_type="text/event-stream")


# ── Routes: Validate (SSE) ────────────────────────────────────────────────

@app.post("/api/validate")
async def run_validate(payload: ConfigPayload = None):
    async def stream():
        try:
            cfg = _config(payload)
            run_id = _get_active_run_id()
            import asyncio
            from src.validator import validate_all

            source = get_source(cfg["source"]["engine"])
            target = get_target(cfg["target"]["engine"])
            await asyncio.to_thread(source.connect, cfg["source"])
            await asyncio.to_thread(target.connect, cfg["target"])
            yield _sse({"type": "log", "msg": "Connected to source and target"})

            report_path = await asyncio.to_thread(validate_all, source, target, cfg, run_id=run_id)
            report = json.loads(report_path.read_text(encoding="utf-8"))

            for r in report.get("tables", []):
                status = "pass" if r["pass"] else "fail"
                yield _sse({"type": "table_result", "result": r})

            yield _sse({"type": "log", "msg": f"Validation report: {report_path.name}"})
            yield _sse({"type": "done", "all_pass": report["all_pass"], "report": str(report_path), "run_id": run_id})
            source.close()
            target.close()
        except Exception as e:
            yield _sse({"type": "error", "msg": traceback.format_exc()})

    return StreamingResponse(stream(), media_type="text/event-stream")


@app.get("/api/dlq/{run_id}/download")
async def download_dlq(run_id: str):
    import shutil
    dlq_dir = ROOT_DIR / "dlq" / run_id
    if not dlq_dir.exists() or not any(dlq_dir.iterdir()):
        return {"error": "No DLQ files found for this run."}
        
    zip_path = ROOT_DIR / "dlq" / f"{run_id}_failed_rows"
    shutil.make_archive(str(zip_path), 'zip', str(dlq_dir))
    
    from starlette.responses import FileResponse
    return FileResponse(
        path=f"{zip_path}.zip", 
        filename=f"migration_dlq_{run_id}.zip", 
        media_type="application/zip"
    )


# ── Serve Frontend (production) ────────────────────────────────────────
# In production, FastAPI serves the Vite-built static files.
# In development, Vite's dev server proxies /api to this backend.

FRONTEND_DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"

if FRONTEND_DIST.exists():
    from fastapi.staticfiles import StaticFiles
    from starlette.responses import FileResponse

    @app.get("/")
    async def serve_index():
        return FileResponse(str(FRONTEND_DIST / "index.html"))

    # Mount static assets (JS, CSS, images)
    app.mount("/assets", StaticFiles(directory=str(FRONTEND_DIST / "assets")), name="assets")

    # Catch-all for SPA routing — must be LAST
    @app.get("/{path:path}")
    async def spa_fallback(path: str):
        file = FRONTEND_DIST / path
        if file.exists() and file.is_file():
            return FileResponse(str(file))
        return FileResponse(str(FRONTEND_DIST / "index.html"))
        # these are for production


# ── Main ───────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")
    import os
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")
