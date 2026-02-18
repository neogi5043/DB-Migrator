"""
Unit tests for the canonical type system.

Tests cover:
  - CANONICAL_TO_TARGET: every canonical type resolves to all 7 targets
  - resolve_target_type: parameterised types (TEXT, DECIMAL) expand correctly
  - Per-source-engine type maps: every map produces valid canonical names
"""
from __future__ import annotations

import pytest

from src.connectors.base import (
    CANONICAL_TO_TARGET,
    resolve_target_type,
    MSSQL_TYPE_MAP,
    POSTGRES_SOURCE_TYPE_MAP,
)

# ── All canonical types the system must handle ────────────────────────
ALL_CANONICAL = [
    "INT8", "INT4", "INT2", "INT1",
    "DECIMAL", "FLOAT8", "FLOAT4",
    "TEXT", "NTEXT", "CHAR",
    "DATE", "DATETIME", "DATETIMETZ",
    "BOOL",
    "BYTES", "VARBYTES",
    "CLOB", "BLOB",
    "JSON", "XML",
]

ALL_TARGETS = ["postgres", "snowflake", "bigquery", "azure_synapse",
               "redshift", "mysql", "mssql"]


# ── CANONICAL_TO_TARGET coverage ──────────────────────────────────────

class TestCanonicalToTarget:
    """Every canonical type must have a mapping for every target engine."""

    @pytest.mark.parametrize("canonical", ALL_CANONICAL)
    def test_canonical_present(self, canonical):
        assert canonical in CANONICAL_TO_TARGET, (
            f"Missing canonical type '{canonical}' in CANONICAL_TO_TARGET")

    @pytest.mark.parametrize("canonical", ALL_CANONICAL)
    @pytest.mark.parametrize("engine", ALL_TARGETS)
    def test_target_mapping_exists(self, canonical, engine):
        entry = CANONICAL_TO_TARGET.get(canonical, {})
        assert engine in entry, (
            f"CANONICAL_TO_TARGET['{canonical}'] missing engine '{engine}'")

    @pytest.mark.parametrize("canonical", ALL_CANONICAL)
    @pytest.mark.parametrize("engine", ALL_TARGETS)
    def test_target_value_not_empty(self, canonical, engine):
        val = CANONICAL_TO_TARGET[canonical][engine]
        assert val and isinstance(val, str), (
            f"Empty or non-string for [{canonical}][{engine}]")


# ── resolve_target_type ───────────────────────────────────────────────

class TestResolveTargetType:
    """Parameterised types should expand {n}, {p}, {s} correctly."""

    def test_text_with_length(self):
        result = resolve_target_type("TEXT", "mysql", length=255)
        assert "255" in result

    def test_decimal_with_precision_scale(self):
        result = resolve_target_type("DECIMAL", "mysql",
                                      precision=18, scale=4)
        assert "18" in result
        assert "4" in result

    def test_plain_type_no_params(self):
        result = resolve_target_type("INT8", "mysql")
        assert result == "BIGINT"

    def test_unknown_canonical_raises(self):
        with pytest.raises(KeyError):
            resolve_target_type("NONEXISTENT_TYPE", "mysql")


# ── Source engine type maps ───────────────────────────────────────────

class TestSourceTypeMaps:
    """Every value in a source type map must be a valid canonical name."""

    @pytest.mark.parametrize("raw,canon", list(MSSQL_TYPE_MAP.items()))
    def test_mssql_map_values(self, raw, canon):
        assert canon in ALL_CANONICAL, (
            f"MSSQL type '{raw}' maps to unknown canonical '{canon}'")

    @pytest.mark.parametrize("raw,canon", list(POSTGRES_SOURCE_TYPE_MAP.items()))
    def test_postgres_map_values(self, raw, canon):
        assert canon in ALL_CANONICAL, (
            f"Postgres type '{raw}' maps to unknown canonical '{canon}'")


# ── Smoke: all source maps are non-empty ──────────────────────────────

class TestSourceMapsNonEmpty:
    def test_mssql_map_has_entries(self):
        assert len(MSSQL_TYPE_MAP) > 0

    def test_postgres_map_has_entries(self):
        assert len(POSTGRES_SOURCE_TYPE_MAP) > 0
