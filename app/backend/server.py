"""
FastAPI backend — thin wrapper around the existing migration CLI modules.

Start:  cd app/backend && python server.py
"""
from __future__ import annotations

import asyncio
import json
import logging
import shutil
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path
from contextlib import redirect_stdout, redirect_stderr
from io import StringIO

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import uvicorn

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

# ── Helpers ────────────────────────────────────────────────────────────────

def _config() -> dict:
    return load_config()


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
    source_engine: str = "postgres"
    source_host: str = ""
    source_port: str = "5432"
    source_db: str = ""
    source_schema: str = ""
    target_engine: str = "mysql"
    target_host: str = ""
    target_port: str = "3306"
    target_db: str = ""
    target_schema: str = ""
    llm_provider: str = "azure_openai"
    llm_model: str = ""
    llm_key: str = ""
    chunk_size: int = 5000
    disable_fk: bool = True


# ── Routes: Config ─────────────────────────────────────────────────────────

@app.get("/api/config")
def get_config():
    try:
        cfg = _config()
        return cfg
    except Exception as e:
        raise HTTPException(500, str(e))


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
async def run_extract():
    async def stream():
        yield _sse({"type": "log", "msg": "Connecting to source database..."})
        try:
            cfg = _config()
            run_id = generate_run_id()
            _set_active_run_id(run_id)
            yield _sse({"type": "log", "msg": f"Run ID: {run_id}"})

            source = get_source(cfg["source"]["engine"])
            source.connect(cfg["source"])
            yield _sse({"type": "log", "msg": f"Connected to {cfg['source']['engine']}"})

            from src.extractor import extract_schema, extract_stats
            yield _sse({"type": "log", "msg": "Extracting schema..."})
            spec_path = extract_schema(source, cfg, run_id=run_id)
            yield _sse({"type": "log", "msg": f"Schema extracted → {spec_path.name}"})

            yield _sse({"type": "log", "msg": "Collecting column statistics..."})
            extract_stats(source, cfg, spec_path, run_id=run_id)
            yield _sse({"type": "log", "msg": "Statistics collected"})

            # Count tables
            spec = json.loads(spec_path.read_text(encoding="utf-8"))
            n_tables = len(spec.get("tables", []))
            n_cols = sum(len(t.get("columns", [])) for t in spec.get("tables", []))
            yield _sse({"type": "log", "msg": f"✓ Extraction complete — {n_tables} tables, {n_cols} columns"})
            yield _sse({"type": "done", "tables": n_tables, "columns": n_cols, "run_id": run_id})
            source.close()
        except Exception as e:
            yield _sse({"type": "error", "msg": str(e)})

    return StreamingResponse(stream(), media_type="text/event-stream")


# ── Routes: Propose (SSE) ─────────────────────────────────────────────────

@app.post("/api/propose")
async def run_propose():
    async def stream():
        try:
            cfg = _config()
            run_id = _get_active_run_id()
            from src.llm_client import build_llm, generate_mapping, translate_sql

            ensure_dirs()
            spec_dir = ROOT_DIR / "schemas" / run_id
            spec_files = list(spec_dir.glob("*.json"))
            if not spec_files:
                yield _sse({"type": "error", "msg": "No schema specs found. Run extract first."})
                return

            llm = build_llm(cfg)
            target_engine = cfg["target"]["engine"]
            target_schema = cfg["target"].get("schema", "public")

            # Run-scoped mapping roots
            draft_root = ROOT_DIR / "mappings" / run_id / "draft"
            approved_root = ROOT_DIR / "mappings" / run_id / "approved"
            draft_root.mkdir(parents=True, exist_ok=True)
            approved_root.mkdir(parents=True, exist_ok=True)

            total = 0
            for spec_path in spec_files:
                spec = json.loads(spec_path.read_text(encoding="utf-8"))
                source_engine = spec["source_engine"]
                for table in spec["tables"]:
                    total += 1

            done = 0
            for spec_path in spec_files:
                spec = json.loads(spec_path.read_text(encoding="utf-8"))
                source_engine = spec["source_engine"]
                for table in spec["tables"]:
                    name = f"{table['schema']}.{table['name']}"
                    yield _sse({"type": "log", "msg": f"Proposing mapping for {name}..."})

                    mapping = generate_mapping(llm, source_engine, target_engine, target_schema, table)
                    mapping["source_engine"] = source_engine
                    mapping["target_engine"] = target_engine
                    mapping["status"] = "draft"

                    out = draft_root / f"{table['name']}.json"
                    out.parent.mkdir(parents=True, exist_ok=True)
                    out.write_text(json.dumps(mapping, indent=2, default=str), encoding="utf-8")

                    done += 1
                    yield _sse({"type": "progress", "done": done, "total": total, "current": table["name"]})
                    yield _sse({"type": "log", "msg": f"✓ {table['name']} — {len(mapping.get('columns', []))} columns"})
                    await asyncio.sleep(0.05)  # yield control

            # Translate views
            for category in ["views", "routines", "triggers"]:
                src_dir = spec_dir / category
                if not src_dir.exists():
                    continue

                draft_dir = draft_root / category
                draft_dir.mkdir(parents=True, exist_ok=True)
                ObjectTypeMap = {"views": "VIEW", "routines": "PROCEDURE/FUNCTION", "triggers": "TRIGGER"}
                for sql_file in src_dir.glob("*.sql"):
                    yield _sse({"type": "log", "msg": f"Translating {category[:-1]}: {sql_file.name}..."})
                    sql_code = sql_file.read_text(encoding="utf-8")
                    translated = translate_sql(
                        llm, cfg["source"]["engine"], cfg["target"]["engine"],
                        sql_code, ObjectTypeMap.get(category, "SQL"),
                        object_name=sql_file.stem.split(".")[-1]
                    )
                    tgt_file = draft_dir / sql_file.name
                    tgt_file.write_text(translated, encoding="utf-8")
                    yield _sse({"type": "log", "msg": f"✓ {sql_file.name} translated"})
                    await asyncio.sleep(0.05)

            yield _sse({"type": "done", "tables": done})
        except Exception as e:
            yield _sse({"type": "error", "msg": str(e)})

    return StreamingResponse(stream(), media_type="text/event-stream")


# ── Routes: Apply Schema (SSE) ────────────────────────────────────────────

@app.post("/api/apply-schema")
async def run_apply_schema():
    async def stream():
        try:
            cfg = _config()
            run_id = _get_active_run_id()
            from src.schema_gen import generate_ddl, apply_schema

            target = get_target(cfg["target"]["engine"])
            target.connect(cfg["target"])
            yield _sse({"type": "log", "msg": f"Connected to target {cfg['target']['engine']}"})

            ddl_paths = generate_ddl(target, cfg, run_id=run_id)
            yield _sse({"type": "log", "msg": f"Generated DDL for {len(ddl_paths)} tables"})

            apply_schema(target, cfg, dry_run=False, run_id=run_id)
            yield _sse({"type": "log", "msg": f"✓ Schema applied ({len(ddl_paths)} tables)"})
            yield _sse({"type": "done", "tables": len(ddl_paths), "run_id": run_id})
            target.close()
        except Exception as e:
            yield _sse({"type": "error", "msg": str(e)})

    return StreamingResponse(stream(), media_type="text/event-stream")


# ── Routes: Migrate (SSE) ─────────────────────────────────────────────────

@app.post("/api/migrate")
async def run_migrate():
    async def stream():
        try:
            cfg = _config()
            from src.migrator import migrate_all

            source = get_source(cfg["source"]["engine"])
            target = get_target(cfg["target"]["engine"])
            source.connect(cfg["source"])
            target.connect(cfg["target"])
            yield _sse({"type": "log", "msg": "Connected to source and target"})

            run_id = _get_active_run_id()
            yield _sse({"type": "log", "msg": f"Migration run: {run_id}"})

            results = migrate_all(source, target, cfg, run_id)
            for r in results:
                yield _sse({
                    "type": "table_done",
                    "table": r["table"],
                    "rows": r["rows_loaded"],
                    "failures": r["failures"],
                })
                yield _sse({"type": "log", "msg": f"✓ {r['table']} — {r['rows_loaded']:,} rows"})

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
async def run_validate():
    async def stream():
        try:
            cfg = _config()
            run_id = _get_active_run_id()
            from src.validator import validate_all

            source = get_source(cfg["source"]["engine"])
            target = get_target(cfg["target"]["engine"])
            source.connect(cfg["source"])
            target.connect(cfg["target"])
            yield _sse({"type": "log", "msg": "Connected to source and target"})

            report_path = validate_all(source, target, cfg, run_id=run_id)
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
    # these are for production


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
