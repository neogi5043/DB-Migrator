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


def extract_schema(source: SourceConnector, config: dict) -> Path:
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

    tables = []
    for t in tables_meta:
        schema = t["schema"]
        name = t["name"]
        log.info("  ► %s.%s", schema, name)

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

    out_path = ROOT_DIR / "schemas" / f"{database}.json"
    out_path.write_text(json.dumps(spec, indent=2, default=str), encoding="utf-8")
    log.info("Schema written to %s", out_path)
    return out_path


def extract_stats(source: SourceConnector, config: dict,
                  spec_path: Path) -> Path:
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

    out_path = ROOT_DIR / "stats" / f"{database}_stats.json"
    out_path.write_text(json.dumps(all_stats, indent=2, default=str), encoding="utf-8")
    log.info("Stats written to %s", out_path)
    return out_path
