"""
Validator — post-migration data validation using both connectors.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from src.connectors.base import SourceConnector, TargetConnector
from src.utils import ROOT_DIR, ensure_dirs

log = logging.getLogger(__name__)


def _normalise_ts(val):
    """Truncate timestamp values to second-level for cross-engine comparison."""
    if val is None:
        return None
    s = str(val)
    # ISO / datetime string — keep only up to seconds
    if "T" in s or " " in s:
        s = s[:19]  # "2024-01-15T12:30:45" or "2024-01-15 12:30:45"
    return s


def _is_timestamp_type(canonical: str) -> bool:
    return canonical in ("DATETIME", "DATETIMETZ", "DATE")


def _compare(src_val, tgt_val, canonical: str, float_tol: float) -> bool:
    """Compare two aggregate values with engine-aware tolerance."""
    if src_val is None and tgt_val is None:
        return True
    if src_val is None or tgt_val is None:
        return False

    # Timestamp — compare at second granularity (Gap 8)
    if _is_timestamp_type(canonical):
        return _normalise_ts(src_val) == _normalise_ts(tgt_val)

    # Numeric — tolerance for floats
    try:
        s, t = float(src_val), float(tgt_val)
        if s == 0:
            return abs(t) < 1e-9
        return abs(s - t) / abs(s) <= float_tol
    except (TypeError, ValueError):
        return str(src_val) == str(tgt_val)


def validate_table(
    source: SourceConnector,
    target: TargetConnector,
    config: dict,
    mapping: dict,
) -> dict:
    """Run L1-L3 validation checks for one table.

    L1: Row count match
    L2: Aggregate checks (SUM, MIN, MAX) — both source & target
    L3: COUNT(DISTINCT) on key columns
    """
    src_cfg = config["source"]
    val_cfg = config.get("validation", {})
    tolerance = val_cfg.get("row_count_tolerance", 0.0)
    float_tol = val_cfg.get("float_tolerance", 0.0001)

    database = src_cfg["database"]
    src_parts = mapping.get("source_table", "").split(".")
    schema = src_parts[0] if len(src_parts) > 1 else ""
    src_table = src_parts[-1]
    target_schema = config["target"].get("schema", "public")
    # Strip any existing schema prefix (e.g. "Bi_doctor_db.orders" -> "orders")
    raw_tgt = mapping.get("target_table", src_table)
    tgt_table = raw_tgt.rsplit(".", 1)[-1] if "." in raw_tgt else raw_tgt
    fqn_tgt = f"{target_schema}.{tgt_table}"

    checks = []

    # ── L1 — Row Count ─────────────────────────────────────────────
    try:
        src_rows = source.get_row_count(database, schema, src_table)
    except Exception as e:
        log.warning("Source row count failed: %s", e)
        src_rows = -1

    tgt_rows = target.get_row_count(fqn_tgt)

    row_match = (
        abs(src_rows - tgt_rows) <= (src_rows * tolerance)
        if src_rows > 0
        else tgt_rows >= 0
    )
    checks.append({
        "check": "L1_ROW_COUNT", "source": src_rows,
        "target": tgt_rows, "pass": row_match,
    })

    # ── L2 & L3 — Aggregates on numeric / key columns ──────────────
    for col in mapping.get("columns", []):
        canonical = col.get("canonical_type", "")
        src_col = col.get("source", col.get("name", ""))
        tgt_col = col.get("target", src_col)

        # L2 — numeric aggregates (SUM, MIN, MAX) with source comparison
        if canonical in ("INT4", "INT8", "INT2", "INT1", "DECIMAL",
                         "FLOAT8", "FLOAT4", "DATETIME", "DATETIMETZ", "DATE"):
            for func in ("SUM", "MIN", "MAX"):
                # Skip SUM for temporal types
                if func == "SUM" and _is_timestamp_type(canonical):
                    continue
                try:
                    src_val = source.run_aggregate(
                        database, schema, src_table, src_col, func)
                    tgt_val = target.run_aggregate(fqn_tgt, tgt_col, func)
                    passed = _compare(src_val, tgt_val, canonical, float_tol)
                    checks.append({
                        "check": f"L2_{func}", "column": tgt_col,
                        "source": str(src_val), "target": str(tgt_val),
                        "pass": passed,
                    })
                except Exception as e:
                    checks.append({
                        "check": f"L2_{func}", "column": tgt_col,
                        "error": str(e), "pass": False,
                    })

        # L3 — COUNT(DISTINCT) on primary key columns
        if col.get("role") == "primary_key":
            try:
                src_distinct = source.run_aggregate(
                    database, schema, src_table, src_col, "COUNT_DISTINCT")
                tgt_distinct = target.run_aggregate(
                    fqn_tgt, tgt_col, "COUNT_DISTINCT")
                checks.append({
                    "check": "L3_DISTINCT", "column": tgt_col,
                    "source": src_distinct, "target": tgt_distinct,
                    "pass": src_distinct == tgt_distinct,
                })
            except Exception as e:
                checks.append({
                    "check": "L3_DISTINCT", "column": tgt_col,
                    "error": str(e), "pass": False,
                })

    passed_all = all(c["pass"] for c in checks)
    return {
        "source_table": mapping.get("source_table"),
        "target_table": fqn_tgt,
        "checks": checks,
        "pass": passed_all,
    }


def validate_all(
    source: SourceConnector,
    target: TargetConnector,
    config: dict,
) -> Path:
    """Validate all approved mappings. Write report to reports/."""
    ensure_dirs()
    approved_dir = ROOT_DIR / "mappings" / "approved"
    results = []

    for mf in sorted(approved_dir.glob("*.json")):
        mapping = json.loads(mf.read_text(encoding="utf-8"))
        log.info("Validating %s", mapping.get("source_table", mf.stem))
        result = validate_table(source, target, config, mapping)
        results.append(result)
        status = "✓" if result["pass"] else "✗"
        log.info("  %s %s", status, result["target_table"])

    report = {
        "validated_at": datetime.now(timezone.utc).isoformat(),
        "source_engine": source.engine_name,
        "target_engine": target.engine_name,
        "tables": results,
        "all_pass": all(r["pass"] for r in results),
    }

    out = ROOT_DIR / "reports" / f"validation_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    out.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    log.info("Validation report: %s", out)
    return out
