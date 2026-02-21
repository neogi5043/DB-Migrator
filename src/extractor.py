"""
Extractor — engine-agnostic schema and column-stats extraction.

Reads from the source connector, writes normalized JSON to schemas/ and stats/.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from src.connectors.base import SourceConnector
from src.utils import ROOT_DIR, ensure_dirs

log = logging.getLogger(__name__)


def extract_schema(
    source: SourceConnector,
    config: dict,
    run_id: str | None = None,
    on_progress=None
) -> Path:
    """Extract full schema spec from the source database.

    Returns the path to the saved JSON file.
    """
    ensure_dirs()
    src_cfg = config["source"]
    database = src_cfg["database"]
    schemas = src_cfg.get("schema_filter", [])

    log.info("Extracting schema from %s database=%s schemas=%s",
             source.engine_name, database, schemas or "ALL")

    tables_meta = source.list_tables(database, schemas)
    log.info("Found %d tables", len(tables_meta))
    total_tables = len(tables_meta)

    tables = []
    for i, t in enumerate(tables_meta):
        schema = t["schema"]
        name = t["name"]
        log.info("  ► %s.%s", schema, name)
        
        if on_progress:
            on_progress(f"Extracting {schema}.{name}...", i, total_tables)

        columns = source.get_columns(database, schema, name)
        pk = source.get_primary_keys(database, schema, name)
        fks = source.get_foreign_keys(database, schema, name)
        indexes = source.get_indexes(database, schema, name)
        raw_ddl = source.get_raw_ddl(database, schema, name)

        tables.append({
            "schema": schema,
            "name": name,
            "table_kind": t.get("table_kind", "T"),
            "comment": t.get("comment", ""),
            "columns": columns,
            "primary_key": pk,
            "foreign_keys": fks,
            "indexes": indexes,
            "raw_ddl": raw_ddl,
        })

    spec = {
        "source_engine": source.engine_name,
        "database": database,
        "extracted_at": datetime.now(timezone.utc).isoformat(),
        "tables": tables,
    }

    base_dir = ROOT_DIR / "schemas"
    if run_id:
        base_dir = base_dir / run_id
    base_dir.mkdir(parents=True, exist_ok=True)

    out_path = base_dir / f"{database}.json"
    out_path.write_text(json.dumps(spec, indent=2, default=str), encoding="utf-8")
    log.info("Schema written to %s", out_path)

    # Also extract views, routines, and triggers into the same run-scoped folder
    extract_views(source, config, run_id=run_id)
    extract_routines(source, config, run_id=run_id)
    extract_triggers(source, config, run_id=run_id)
    
    return out_path


def extract_views(
    source: SourceConnector,
    config: dict,
    run_id: str | None = None,
) -> None:
    """Extract view definitions from the source database."""
    src_cfg = config["source"]
    database = src_cfg["database"]
    schemas = src_cfg.get("schema_filter", [])
    if not schemas:
        schemas = ["public"]

    log.info("Extracting views... %s", schemas)
    views_base = ROOT_DIR / "schemas"
    if run_id:
        views_base = views_base / run_id
    views_dir = views_base / "views"
    views_dir.mkdir(parents=True, exist_ok=True)

    for schema in schemas:
        views = source.list_views(database, schema)
        for v in views:
            name = v["name"]
            log.info("  ► View: %s.%s", schema, name)
            definition = source.get_view_definition(database, schema, name)
            if definition:
                out_file = views_dir / f"{schema}.{name}.sql"
                out_file.write_text(definition, encoding="utf-8")


def extract_routines(
    source: SourceConnector,
    config: dict,
    run_id: str | None = None,
) -> None:
    """Extract routine (function/procedure) definitions."""
    src_cfg = config["source"]
    database = src_cfg["database"]
    schemas = src_cfg.get("schema_filter", [])
    if not schemas:
        schemas = ["public"]

    log.info("Extracting routines... %s", schemas)
    routines_base = ROOT_DIR / "schemas"
    if run_id:
        routines_base = routines_base / run_id
    routines_dir = routines_base / "routines"
    routines_dir.mkdir(parents=True, exist_ok=True)

    for schema in schemas:
        routines = source.list_routines(database, schema)
        for r in routines:
            name = r["name"]
            rtype = r["type"]
            log.info("  ► %s: %s.%s", rtype, schema, name)
            definition = source.get_routine_definition(database, schema, name)
            if definition:
                out_file = routines_dir / f"{schema}.{name}.sql"
                out_file.write_text(definition, encoding="utf-8")


def extract_triggers(
    source: SourceConnector,
    config: dict,
    run_id: str | None = None,
) -> None:
    """Extract trigger definitions."""
    src_cfg = config["source"]
    database = src_cfg["database"]
    schemas = src_cfg.get("schema_filter", [])
    if not schemas:
        schemas = ["public"]

    log.info("Extracting triggers... %s", schemas)
    triggers_base = ROOT_DIR / "schemas"
    if run_id:
        triggers_base = triggers_base / run_id
    triggers_dir = triggers_base / "triggers"
    triggers_dir.mkdir(parents=True, exist_ok=True)

    for schema in schemas:
        triggers = source.list_triggers(database, schema)
        for t in triggers:
            name = t["name"]
            table = t["table"]
            log.info("  ► Trigger: %s on %s.%s", name, schema, table)
            definition = source.get_trigger_definition(database, schema, name, table)
            if definition:
                out_file = triggers_dir / f"{schema}.{table}.{name}.sql"
                out_file.write_text(definition, encoding="utf-8")


def extract_stats(
    source: SourceConnector,
    config: dict,
    spec_path: Path,
    run_id: str | None = None,
) -> Path:
    """Collect column statistics for all tables in the schema spec.

    Returns the path to the saved stats JSON.
    """
    ensure_dirs()
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    database = spec["database"]
    sample = config.get("validation", {}).get("sample_rows", 1000)

    all_stats: dict = {}
    for table in spec["tables"]:
        schema = table["schema"]
        name = table["name"]
        col_names = [c["name"] for c in table["columns"]]
        log.info("  ► stats for %s.%s (%d cols)", schema, name, len(col_names))
        stats = source.get_column_stats(database, schema, name, col_names, sample)
        all_stats[f"{schema}.{name}"] = stats

    stats_dir = ROOT_DIR / "stats"
    if run_id:
        stats_dir = stats_dir / run_id
    stats_dir.mkdir(parents=True, exist_ok=True)

    out_path = stats_dir / f"{database}_stats.json"
    out_path.write_text(json.dumps(all_stats, indent=2, default=str), encoding="utf-8")
    log.info("Stats written to %s", out_path)
    return out_path
