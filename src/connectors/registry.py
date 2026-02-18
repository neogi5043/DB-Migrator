"""
Connector registry — maps engine-name strings from config.yaml to classes.

Adding a new engine = one import + one dict entry here.
"""
from __future__ import annotations

from src.connectors.base import SourceConnector, TargetConnector

# ── Source connectors ──────────────────────────────────────────────────
from src.connectors.source.mssql import MSSQLSourceConnector
from src.connectors.source.postgres import PostgresSourceConnector

# ── Target connectors ─────────────────────────────────────────────────
from src.connectors.target.mysql import MySQLTargetConnector

SOURCE_REGISTRY: dict[str, type[SourceConnector]] = {
    "mssql":    MSSQLSourceConnector,
    "postgres": PostgresSourceConnector,
}

TARGET_REGISTRY: dict[str, type[TargetConnector]] = {
    "mysql": MySQLTargetConnector,
}


def get_source(engine: str) -> SourceConnector:
    """Instantiate and return the source connector for *engine*."""
    cls = SOURCE_REGISTRY.get(engine)
    if not cls:
        raise ValueError(
            f"Unknown source engine: '{engine}'.  "
            f"Available: {', '.join(SOURCE_REGISTRY)}"
        )
    return cls()


def get_target(engine: str) -> TargetConnector:
    """Instantiate and return the target connector for *engine*."""
    cls = TARGET_REGISTRY.get(engine)
    if not cls:
        raise ValueError(
            f"Unknown target engine: '{engine}'.  "
            f"Available: {', '.join(TARGET_REGISTRY)}"
        )
    return cls()
