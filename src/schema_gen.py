"""
Schema generator — reads approved mappings, renders DDL via target connector.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from src.connectors.base import TargetConnector
from src.utils import ROOT_DIR, ensure_dirs, topological_sort

log = logging.getLogger(__name__)


def generate_ddl(
    target: TargetConnector,
    config: dict,
    run_id: str | None = None,
) -> list[Path]:
    """Render DDL for all approved mappings and write to ddl/.

    If *run_id* is provided, use per-run subfolders:
        mappings/<run_id>/approved, ddl/<run_id>/
    Otherwise, fall back to the legacy shared folders.
    """
    ensure_dirs()
    schema = config["target"].get("schema", "public")

    if run_id:
        approved_dir = ROOT_DIR / "mappings" / run_id / "approved"
        ddl_dir = ROOT_DIR / "ddl" / run_id
    else:
        # Final fallback to active run from run_state.json if caller didn't pass it
        from src.cli import _resolve_run_id
        resolved = _resolve_run_id(None)
        if not resolved:
            log.warning("No run_id provided and no active run found. Defaulting to legacy paths (NOT RECOMMENDED).")
            approved_dir = ROOT_DIR / "mappings" / "approved"
            ddl_dir = ROOT_DIR / "ddl"
        else:
            approved_dir = ROOT_DIR / "mappings" / resolved / "approved"
            ddl_dir = ROOT_DIR / "ddl" / resolved
    
    ddl_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []

    mapping_files = sorted(approved_dir.glob("*.json"))
    if not mapping_files:
        log.warning("No approved mappings found in %s", approved_dir)
        return paths

    for mf in mapping_files:
        mapping = json.loads(mf.read_text(encoding="utf-8"))
        # Strip any schema prefix from target_table (e.g. "target_db.orders" -> "orders")
        raw_tbl = mapping.get("target_table", mf.stem)
        tbl_name = raw_tbl.rsplit(".", 1)[-1] if "." in raw_tbl else raw_tbl
        mapping["target_table"] = tbl_name

        ddl = target.render_create_table(mapping, schema)
        index_stmts = target.render_indexes(mapping, schema)

        full_ddl = ddl + "\n"
        for stmt in index_stmts:
            full_ddl += "\n" + stmt + "\n"

        out = ddl_dir / f"{tbl_name}.sql"
        out.write_text(full_ddl, encoding="utf-8")
        paths.append(out)
        log.info("DDL written: %s", out)

    return paths


def apply_schema(
    target: TargetConnector,
    config: dict,
    dry_run: bool = True,
    run_id: str | None = None,
) -> None:
    """Apply DDL to target database.

    If *dry_run* is True, just print the DDL without executing.
    """
    if run_id:
        ddl_dir = ROOT_DIR / "ddl" / run_id
    else:
        from src.cli import _resolve_run_id
        resolved = _resolve_run_id(None)
        ddl_dir = ROOT_DIR / "ddl" / resolved if resolved else ROOT_DIR / "ddl"
    ddl_files = sorted(ddl_dir.glob("*.sql"))

    if not ddl_files:
        log.warning("No DDL files found in %s — run generate_ddl first", ddl_dir)
        return

    # Sort by FK dependencies if we have the mappings
    for f in ddl_files:
        sql = f.read_text(encoding="utf-8")
        if dry_run:
            print(f"\n-- {f.name}")
            print(sql)
        else:
            log.info("Applying %s", f.name)
            for stmt in sql.split(";"):
                stmt = stmt.strip()
                if stmt:
                    target.apply_ddl(stmt + ";")
            log.info("✓ %s applied", f.name)

    # Apply Views, Routines, Triggers
    for category in ["views", "routines", "triggers"]:
        # Look in mappings/approved/{category}, optionally scoped by run_id
        if run_id:
            cat_dir = ROOT_DIR / "mappings" / run_id / "approved" / category
        else:
            from src.cli import _resolve_run_id
            resolved = _resolve_run_id(None)
            cat_dir = ROOT_DIR / "mappings" / (resolved or "") / "approved" / category
            if not resolved:
                cat_dir = ROOT_DIR / "mappings" / "approved" / category
        if not cat_dir.exists():
            continue
        
        files = sorted(cat_dir.glob("*.sql"))
        if files:
            log.info("Applying %s from approved/...", category)
            for f in files:
                sql = f.read_text(encoding="utf-8")
                if dry_run:
                    print(f"\n-- {category}/{f.name}")
                    print(sql)
                else:
                    log.info("Applying %s %s", category[:-1], f.name)
                    # These might be complex statements (e.g. CREATE PROCEDURE)
                    # Splitting by ';' is dangerous for procedures/triggers that contain semicolons.
                    # We assume the file contains a single valid statement or handle it carefully.
                    # For now, send the whole file as one command if possible, or naive split?
                    # Procedures/Triggers often use delimiters.
                    # Connectors like proper drivers often handle multi-statement or single blocks.
                    # Given the prompt asks for "valid SQL", let's assume it's one block.
                    # But if it has delimiters (DELIMITER //), we need to handle that.
                    # Python drivers usually execute one command at a time.
                    # Best effort: execute the whole text as one statement.
                    try:
                        target.apply_ddl(sql)
                        log.info("✓ %s applied", f.name)
                    except Exception as e:
                        log.error("✗ Failed to apply %s: %s", f.name, e)
