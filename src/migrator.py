"""
Migrator — chunked extract-transform-load with checkpoint resume.

Uses OFFSET/LIMIT chunking so it works with any PK type (text, UUID, int).
"""
from __future__ import annotations

import csv
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from src.connectors.base import SourceConnector, TargetConnector
from src.utils import ROOT_DIR, ensure_dirs, generate_run_id

log = logging.getLogger(__name__)

CHECKPOINT_DIR = ROOT_DIR / "checkpoints"


def _checkpoint_path(run_id: str, table: str) -> Path:
    d = CHECKPOINT_DIR / run_id
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{table}.json"


def _load_checkpoint(run_id: str, table: str) -> int:
    """Return the last completed offset, or 0 if none."""
    p = _checkpoint_path(run_id, table)
    if p.exists():
        data = json.loads(p.read_text())
        return data.get("last_offset", 0)
    return 0


def _save_checkpoint(run_id: str, table: str, last_offset: int, rows_loaded: int) -> None:
    p = _checkpoint_path(run_id, table)
    p.write_text(json.dumps({
        "table": table, "last_offset": last_offset,
        "rows_loaded": rows_loaded,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }))


def _apply_transforms(rows: list[dict], columns: list[dict]) -> list[dict]:
    """Apply type coercions per the mapping spec using Polars vectorization."""
    if not rows:
        return []
        
    import polars as pl
    
    # Fast load into dataframe, inferring schema from the first 500 rows.
    # Unmatched objects (LOBs, specific precision Decimals) default to Object space
    df = pl.from_dicts(rows, infer_schema_length=500)
    
    exprs = []
    rename_map = {}
    target_cols = []
    
    for col in columns:
        name = col.get("target", col.get("source", ""))
        src_name = col.get("source", name)
        target_cols.append(name)
        
        if src_name not in df.columns:
            exprs.append(pl.lit(None).alias(name))
            continue
            
        if src_name != name:
            rename_map[src_name] = name
            
        canonical = col.get("canonical_type", "")
        dt = df.schema.get(src_name)
        
        # Boolean coercion
        if canonical == "BOOL" and dt in [pl.Int8, pl.Int16, pl.Int32, pl.Int64]:
            exprs.append(pl.col(src_name).cast(pl.Boolean).alias(src_name))
            
        # Decimal -> Float 
        elif dt == pl.Decimal:
            exprs.append(pl.col(src_name).cast(pl.Float64).alias(src_name))
            
        # Struct -> JSON String
        elif isinstance(dt, pl.Struct):
            exprs.append(
                pl.col(src_name).map_elements(
                    lambda x: json.dumps(x) if x else None, 
                    return_dtype=pl.Utf8
                ).alias(src_name)
            )
            
        # Unknown/Object (LOBs, un-inferred Python Decimals/Dicts/Lists)
        elif dt == pl.Object:
            def _coerce_obj(val):
                if hasattr(val, "read"): return val.read()
                if hasattr(val, "as_integer_ratio") and not isinstance(val, (int, float)): return float(val)
                if isinstance(val, dict): return json.dumps(val)
                return val
            exprs.append(
                pl.col(src_name).map_elements(_coerce_obj, return_dtype=pl.Object).alias(src_name)
            )

    if exprs:
        df = df.with_columns(exprs)
        
    if rename_map:
        df = df.rename(rename_map)
        
    # Keep only target columns ensuring they exist in the dataframe
    final_cols = [c for c in target_cols if c in df.columns]
    
    # Return as list of standard python dictionaries
    return df.select(final_cols).to_dicts()


def _handle_dead_letter(run_id: str, table_name: str, offset: int, rows: list[dict]):
    import csv
    dlq_dir = ROOT_DIR / "dlq" / run_id
    dlq_dir.mkdir(parents=True, exist_ok=True)
    out_file = dlq_dir / f"{table_name}_offset_{offset}.csv"
    
    if not rows:
        return
        
    with open(out_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    log.error("Wrote %d failed rows to Dead Letter Queue: %s", len(rows), out_file)


def migrate_table(
    source: SourceConnector,
    target: TargetConnector,
    config: dict,
    mapping: dict,
    run_id: str,
) -> dict:
    """Migrate a single table in chunks using OFFSET/LIMIT."""
    src_cfg = config["source"]
    mig_cfg = config.get("migration", {})
    chunk_size = mig_cfg.get("chunk_size", 100_000)
    max_failures = mig_cfg.get("max_chunk_failures", 5)
    disable_fk = mig_cfg.get("disable_fk_during_load", True)

    database = src_cfg["database"]
    src_table_fqn = mapping.get("source_table", "")
    schema = src_table_fqn.split(".")[0] if "." in src_table_fqn else ""
    table = src_table_fqn.split(".")[-1]
    # Strip any existing schema prefix (e.g. "Bi_doctor_db.orders" -> "orders")
    raw_target = mapping.get("target_table", table)
    target_table = raw_target.rsplit(".", 1)[-1] if "." in raw_target else raw_target
    target_schema = config["target"].get("schema", "public")
    fqn_target = f"{target_schema}.{target_table}"

    columns = mapping.get("columns", [])

    log.info("Migrating %s.%s → %s (chunk=%d)",
             schema, table, fqn_target, chunk_size)

    if disable_fk:
        try:
            target.disable_fk_constraints(fqn_target)
        except Exception as e:
            log.warning("FK disable failed (may be fine): %s", e)

    total_loaded = 0
    failures = 0
    offset = _load_checkpoint(run_id, target_table)
    
    from tenacity import retry, stop_after_attempt, wait_exponential
    
    @retry(
        stop=stop_after_attempt(max_failures),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        reraise=True
    )
    def load_with_retry(fqn, t_cols, r_data):
        return target.bulk_load(fqn, t_cols, r_data)

    while True:
        try:
            rows = source.extract_chunk(
                database, schema, table, columns,
                None, None, offset, chunk_size
            )
        except Exception as e:
            log.error("Extract failed at offset %d: %s", offset, e)
            raise RuntimeError(f"Extraction failed at offset {offset}") from e

        if not rows:
            log.info("No more rows at offset=%d — %s complete (%d rows)",
                     offset, table, total_loaded)
            break

        rows = _apply_transforms(rows, columns)
        target_cols = [c.get("target", c.get("source")) for c in columns]

        try:
            loaded = load_with_retry(fqn_target, target_cols, rows)
            
            # ❗ CRITICAL FIX: Only increment offset on success
            total_loaded += loaded
            offset += len(rows)
            _save_checkpoint(run_id, target_table, offset, total_loaded)
            log.info("  offset %d: %d rows loaded (total %d)",
                     offset, loaded, total_loaded)
                     
        except Exception as e:
            log.error("Target load exhausted retries at offset %d: %s", offset, e)
            
            # Quick check for missing table vs bad row data
            err_msg = str(e).lower()
            if "doesn't exist" in err_msg or "not found" in err_msg or "1146" in err_msg:
                log.error("Fatal error: Target table %s missing.", table)
            else:
                _handle_dead_letter(run_id, target_table, offset, rows)
                
            raise RuntimeError(f"Migration aborted for {table} due to unrecoverable load error") from e

    if disable_fk:
        try:
            target.enable_fk_constraints(fqn_target)
        except Exception:
            pass

    return {"table": target_table, "rows_loaded": total_loaded,
            "failures": failures, "run_id": run_id}


def migrate_all(
    source: SourceConnector,
    target: TargetConnector,
    config: dict,
    run_id: str | None = None,
    tables_filter: list[str] | None = None,
) -> list[dict]:
    """Migrate all approved tables (or a filtered subset).

    If *run_id* is provided, read approved mappings from
    ``mappings/<run_id>/approved``. Otherwise, use the legacy
    shared folder ``mappings/approved``.
    """
    ensure_dirs()
    if not run_id:
        from src.cli import _resolve_run_id
        resolved = _resolve_run_id(None)
        run_id = resolved or generate_run_id()
    log.info("Migration run: %s", run_id)

    if run_id:
        approved_dir = ROOT_DIR / "mappings" / run_id / "approved"
    else:
        from src.cli import _resolve_run_id
        resolved = _resolve_run_id(None)
        if not resolved:
            approved_dir = ROOT_DIR / "mappings" / "approved"
        else:
            approved_dir = ROOT_DIR / "mappings" / resolved / "approved"
            run_id = resolved
    results = []

    for mf in sorted(approved_dir.glob("*.json")):
        mapping = json.loads(mf.read_text(encoding="utf-8"))
        src_table = mapping.get("source_table", mf.stem)
        if tables_filter and src_table not in tables_filter:
            continue
        result = migrate_table(source, target, config, mapping, run_id)
        results.append(result)

    log.info("Migration complete. %d tables processed.", len(results))
    return results
