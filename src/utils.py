"""
Utility helpers: config loading, logging, topological sort, run-id.
"""
from __future__ import annotations

import logging
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

import yaml
from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent.parent  # project root


def setup_logging(level: str = "INFO") -> None:
    """Configure structured logging for the pipeline."""
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )


def load_config(path: str | Path | None = None) -> dict:
    """Load config.yaml and expand ``${ENV_VAR}`` references."""
    load_dotenv(ROOT_DIR / ".env")
    path = Path(path) if path else ROOT_DIR / "config.yaml"
    raw = path.read_text(encoding="utf-8")
    # Replace ${VAR} with environment variable values
    raw = re.sub(
        r"\$\{(\w+)\}",
        lambda m: os.environ.get(m.group(1), m.group(0)),
        raw,
    )
    return yaml.safe_load(raw)


def generate_run_id() -> str:
    """Return a short, timestamped run identifier."""
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    short = uuid.uuid4().hex[:6]
    return f"run-{ts}-{short}"


def topological_sort(tables: list[dict]) -> list[dict]:
    """Sort tables so that FK parents come before children.

    Each table dict must have ``name`` and ``foreign_keys`` (list of dicts
    with a ``parent_table`` field).  Tables with no FK deps come first.
    """
    by_name: dict[str, dict] = {t["name"]: t for t in tables}
    visited: set[str] = set()
    order: list[str] = []

    def _visit(name: str) -> None:
        if name in visited:
            return
        visited.add(name)
        tbl = by_name.get(name)
        if tbl:
            for fk in tbl.get("foreign_keys", []):
                parent = fk.get("parent_table", "")
                if parent in by_name:
                    _visit(parent)
        order.append(name)

    for t in tables:
        _visit(t["name"])
    return [by_name[n] for n in order if n in by_name]


def ensure_dirs() -> None:
    """Create output directories if they don't exist."""
    for d in ("schemas", "stats", "ddl", "reports"):
        (ROOT_DIR / d).mkdir(parents=True, exist_ok=True)
