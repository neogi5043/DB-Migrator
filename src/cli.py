"""
CLI entry point — all migration pipeline commands.

Usage:
    python src/cli.py extract
    python src/cli.py propose
    python src/cli.py validate-mapping [path]
    python src/cli.py apply-schema --dry-run | --apply
    python src/cli.py migrate [--tables <t1,t2>] [--run-id <id>]
    python src/cli.py validate
    python src/cli.py show-checkpoints --run-id <id>
    python src/cli.py list-engines
"""
# test commit
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

# Allow running as `python src/cli.py` from project root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.utils import load_config, setup_logging, ensure_dirs, generate_run_id, ROOT_DIR


def _resolve_run_id(args) -> str | None:
    """Resolve run_id from args or run_state.json."""
    run_id = getattr(args, "run_id", None)
    if run_id:
        return run_id
    
    state_file = ROOT_DIR / "run_state.json"
    if state_file.exists():
        try:
            data = json.loads(state_file.read_text(encoding="utf-8"))
            return data.get("run_id")
        except Exception:
            pass
    return None
from src.connectors.registry import get_source, get_target, SOURCE_REGISTRY, TARGET_REGISTRY


def cmd_extract(args, config):
    """Extract schema + stats from source database."""
    from src.extractor import extract_schema, extract_stats

    run_id = getattr(args, "run_id", None) or generate_run_id()
    print(f"Run ID: {run_id}")

    source = get_source(config["source"]["engine"])
    source.connect(config["source"])
    try:
        spec_path = extract_schema(source, config, run_id=run_id)
        extract_stats(source, config, spec_path, run_id=run_id)
        print(f"✓ Schema extracted to {spec_path}")
    finally:
        source.close()


def cmd_propose(args, config):
    """Generate LLM-powered mapping proposals for each table."""
    from src.llm_client import build_llm, generate_mapping

    run_id = _resolve_run_id(args) or generate_run_id()

    ensure_dirs()
    spec_dir = ROOT_DIR / "schemas" / run_id
    if not spec_dir.exists():
        # Fallback to legacy shared folder ONLY for reading schemas if run-scoped one missing
        # (Allows manual schema placement)
        if not (ROOT_DIR / "schemas").exists():
            print("✗ No schema specs found. Run 'extract' first.")
            return
        spec_dir = ROOT_DIR / "schemas"

    spec_files = list(spec_dir.glob("*.json"))
    if not spec_files:
        print(f"✗ No schema specs found in {spec_dir}. Run 'extract' first.")
        return

    llm = build_llm(config)
    target_engine = config["target"]["engine"]
    target_schema = config["target"].get("schema", "public")

    # Run-scoped mapping roots ONLY
    draft_root = ROOT_DIR / "mappings" / run_id / "draft"
    approved_root = ROOT_DIR / "mappings" / run_id / "approved"

    draft_root.mkdir(parents=True, exist_ok=True)
    approved_root.mkdir(parents=True, exist_ok=True)

    for spec_path in spec_files:
        spec = json.loads(spec_path.read_text(encoding="utf-8"))
        source_engine = spec["source_engine"]

        for table in spec["tables"]:
            print(f"  ► Proposing mapping for {table['schema']}.{table['name']}…")
            try:
                mapping = generate_mapping(
                    llm, source_engine, target_engine, target_schema, table
                )
                mapping["source_engine"] = source_engine
                mapping["target_engine"] = target_engine
                mapping["status"] = "draft"
                mapping["prompt_version"] = config["llm"].get("prompt_version", "v1")

                out = draft_root / f"{table['name']}.json"
                out.write_text(json.dumps(mapping, indent=2, default=str), encoding="utf-8")
                print(f"    ✓ Written to {out}")
            except Exception as e:
                print(f"    ✗ Failed: {e}")

    print(f"\nDraft mappings saved in {draft_root}/.")

    # -------------------------------------------------------------------------
    # PART 2: Translate Views & Routines
    # -------------------------------------------------------------------------
    print("\n=== Translating Views & Routines ===")
    from src.llm_client import translate_sql

    for category in ["views", "routines", "triggers"]:
        # Source SQL lives under the same schemas root (optionally run-scoped)
        src_dir = spec_dir / category
        if not src_dir.exists():
            continue
        
        # Output to mappings/.../draft/{category}
        draft_dir = draft_root / category
        draft_dir.mkdir(parents=True, exist_ok=True)
        
        # Ensure approved dir exists for user convenience
        approved_dir = approved_root / category
        approved_dir.mkdir(parents=True, exist_ok=True)

        ObjectTypeMap = {
            "views": "VIEW",
            "routines": "PROCEDURE/FUNCTION",
            "triggers": "TRIGGER"
        }

        for sql_file in src_dir.glob("*.sql"):
            print(f"  ► Translating {category[:-1]} {sql_file.name}…")
            try:
                sql_code = sql_file.read_text(encoding="utf-8")
                translated = translate_sql(
                    llm, 
                    config["source"]["engine"], 
                    config["target"]["engine"], 
                    sql_code, 
                    ObjectTypeMap.get(category, "SQL"),
                    # Strip schema prefix (e.g. "public.view_name" -> "view_name")
                    object_name=sql_file.stem.split(".")[-1]
                )
                
                tgt_file = draft_dir / sql_file.name
                tgt_file.write_text(translated, encoding="utf-8")
                print(f"    ✓ Written to {tgt_file}")
            except Exception as e:
                print(f"    ✗ Failed: {e}")

    print(f"\nReview generated SQL in {draft_root}/.")
    print(f"Move approved table mappings AND sql files to {approved_root}/.")


def cmd_validate_mapping(args, config):
    """Validate mapping JSON structure."""
    run_id = _resolve_run_id(args)
    if args.path:
        path = Path(args.path)
    else:
        if not run_id:
            print("✗ No run-id specified and no active run found in run_state.json.")
            return
        path = ROOT_DIR / "mappings" / run_id / "approved"
    files = list(path.glob("*.json")) if path.is_dir() else [path]

    if not files:
        print(f"✗ No JSON files found at {path}")
        return

    errors = 0
    for f in files:
        try:
            mapping = json.loads(f.read_text(encoding="utf-8"))
            required = ["source_table", "target_table", "columns"]
            missing = [k for k in required if k not in mapping]
            if missing:
                print(f"  ✗ {f.name}: missing keys: {missing}")
                errors += 1
            else:
                col_count = len(mapping["columns"])
                print(f"  ✓ {f.name}: {col_count} columns")
        except json.JSONDecodeError as e:
            print(f"  ✗ {f.name}: invalid JSON ({e})")
            errors += 1

    if errors:
        print(f"\n{errors} file(s) with errors.")
    else:
        print(f"\n✓ All {len(files)} mapping(s) valid.")


def cmd_apply_schema(args, config):
    """Generate and optionally apply DDL to target."""
    from src.schema_gen import generate_ddl, apply_schema

    run_id = _resolve_run_id(args)

    target = get_target(config["target"]["engine"])
    if not args.dry_run:
        target.connect(config["target"])

    try:
        ddl_paths = generate_ddl(target, config, run_id=run_id)
        if not ddl_paths:
            print("✗ No approved mappings to generate DDL from.")
            return

        if args.dry_run:
            print("=== DRY RUN — DDL preview ===")
            apply_schema(target, config, dry_run=True, run_id=run_id)
        else:
            apply_schema(target, config, dry_run=False, run_id=run_id)
            print(f"✓ Schema applied ({len(ddl_paths)} tables)")
    finally:
        if not args.dry_run:
            target.close()


def cmd_migrate(args, config):
    """Run data migration."""
    from src.migrator import migrate_all

    source = get_source(config["source"]["engine"])
    target = get_target(config["target"]["engine"])
    source.connect(config["source"])
    target.connect(config["target"])

    tables_filter = args.tables.split(",") if args.tables else None
    run_id = _resolve_run_id(args) or generate_run_id()

    try:
        results = migrate_all(source, target, config, run_id, tables_filter)
        print(f"\n{'Table':<40} {'Rows':>10} {'Failures':>10}")
        print("-" * 62)
        for r in results:
            print(f"{r['table']:<40} {r['rows_loaded']:>10} {r['failures']:>10}")
        print(f"\nRun ID: {run_id}")
    finally:
        source.close()
        target.close()


def cmd_validate(args, config):
    """Run post-migration validation."""
    from src.validator import validate_all

    run_id = _resolve_run_id(args)

    source = get_source(config["source"]["engine"])
    target = get_target(config["target"]["engine"])
    source.connect(config["source"])
    target.connect(config["target"])

    try:
        report_path = validate_all(source, target, config, run_id=run_id)
        report = json.loads(report_path.read_text())
        status = "✓ ALL PASS" if report["all_pass"] else "✗ FAILURES"
        print(f"\nValidation: {status}")
        print(f"Report: {report_path}")
    finally:
        source.close()
        target.close()


def cmd_show_checkpoints(args, config):
    """Show checkpoint status for a migration run."""
    run_id = args.run_id
    cp_dir = ROOT_DIR / "checkpoints" / run_id
    if not cp_dir.exists():
        print(f"✗ No checkpoints found for run: {run_id}")
        return

    print(f"Checkpoints for {run_id}:\n")
    print(f"{'Table':<40} {'Last PK':>12} {'Rows':>10} {'Updated'}")
    print("-" * 80)
    for f in sorted(cp_dir.glob("*.json")):
        data = json.loads(f.read_text())
        print(f"{data['table']:<40} {data['last_end']:>12} "
              f"{data['rows_loaded']:>10} {data['updated_at']}")


def cmd_list_engines(args, config):
    """List all registered source and target connectors."""
    print("Source Connectors:")
    for name, cls in SOURCE_REGISTRY.items():
        print(f"  • {name:<20} ({cls.__module__})")
    print(f"\nTarget Connectors:")
    for name, cls in TARGET_REGISTRY.items():
        print(f"  • {name:<20} ({cls.__module__})")
    print(f"\nTotal: {len(SOURCE_REGISTRY)} sources, {len(TARGET_REGISTRY)} targets")


def cmd_clean(args, config):
    """Clean all generated artifacts (schemas, mappings, stats, reports)."""
    import shutil
    
    dirs = ["schemas", "stats", "mappings", "reports", "checkpoints"]
    for d in dirs:
        path = ROOT_DIR / d
        if path.exists():
            print(f"Removing {path}...")
            shutil.rmtree(path)
    print("✓ Project state cleaned.")


def main():
    parser = argparse.ArgumentParser(
        description="Universal Database Migration Framework",
        prog="db-migrate",
    )
    parser.add_argument("--config", default=None, help="Path to config.yaml")
    sub = parser.add_subparsers(dest="command")

    p_ex = sub.add_parser("extract", help="Extract schema + stats from source")
    p_ex.add_argument(
        "--run-id",
        default=None,
        help="Run identifier for per-run folders (schemas/, stats/, etc.)",
    )

    p_pr = sub.add_parser("propose", help="Generate LLM mapping proposals")
    p_pr.add_argument(
        "--run-id",
        default=None,
        help="Run identifier used when extracting schema (for per-run folders)",
    )
    sub.add_parser("clean", help="Clean generated artifacts")

    p_vm = sub.add_parser("validate-mapping", help="Validate mapping files")
    p_vm.add_argument("path", nargs="?", default=None)
    p_vm.add_argument(
        "--run-id",
        default=None,
        help="Run identifier to select mappings/<run-id>/approved",
    )

    p_as = sub.add_parser("apply-schema", help="Generate and apply DDL")
    p_as.add_argument("--dry-run", action="store_true", default=True)
    p_as.add_argument("--apply", action="store_true")
    p_as.add_argument(
        "--run-id",
        default=None,
        help="Run identifier for per-run mappings/ and ddl/ folders",
    )

    p_mg = sub.add_parser("migrate", help="Run data migration")
    p_mg.add_argument("--tables", default=None, help="Comma-separated table filter")
    p_mg.add_argument(
        "--run-id",
        default=None,
        help=(
            "Run identifier for checkpoints and per-run mappings/. "
            "If omitted, a new run-id is generated."
        ),
    )

    p_val = sub.add_parser("validate", help="Post-migration validation")
    p_val.add_argument(
        "--run-id",
        default=None,
        help="Run identifier to select per-run mappings/ and reports/",
    )

    p_cp = sub.add_parser("show-checkpoints", help="Show checkpoint status")
    p_cp.add_argument("--run-id", required=True)

    sub.add_parser("list-engines", help="List registered connectors")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        return

    setup_logging()
    config = load_config(args.config)

    # Handle --apply flag
    if args.command == "apply-schema" and args.apply:
        args.dry_run = False

    cmds = {
        "extract": cmd_extract,
        "propose": cmd_propose,
        "clean": cmd_clean,
        "validate-mapping": cmd_validate_mapping,
        "apply-schema": cmd_apply_schema,
        "migrate": cmd_migrate,
        "validate": cmd_validate,
        "show-checkpoints": cmd_show_checkpoints,
        "list-engines": cmd_list_engines,
    }

    cmds[args.command](args, config)


if __name__ == "__main__":
    main()
