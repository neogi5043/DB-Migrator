"""
Abstract base classes for source and target connectors, plus the
canonical type system that makes the entire pipeline engine-agnostic.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


# ---------------------------------------------------------------------------
# Canonical Type -> Target Engine native type mapping
# Each target connector also uses this at DDL-render time.
# ---------------------------------------------------------------------------
CANONICAL_TO_TARGET: dict[str, dict[str, str]] = {
    "INT8":          {"postgres": "BIGINT",           "snowflake": "NUMBER(18,0)",      "bigquery": "INT64",          "azure_synapse": "BIGINT",          "redshift": "BIGINT",          "mysql": "BIGINT",         "mssql": "BIGINT"},
    "INT4":          {"postgres": "INTEGER",          "snowflake": "NUMBER(9,0)",       "bigquery": "INT64",          "azure_synapse": "INT",             "redshift": "INTEGER",         "mysql": "INT",            "mssql": "INT"},
    "INT2":          {"postgres": "SMALLINT",         "snowflake": "NUMBER(5,0)",       "bigquery": "INT64",          "azure_synapse": "SMALLINT",        "redshift": "SMALLINT",        "mysql": "SMALLINT",       "mssql": "SMALLINT"},
    "INT1":          {"postgres": "SMALLINT",         "snowflake": "NUMBER(3,0)",       "bigquery": "INT64",          "azure_synapse": "TINYINT",         "redshift": "SMALLINT",        "mysql": "TINYINT",        "mssql": "TINYINT"},
    "DECIMAL":       {"postgres": "NUMERIC({p},{s})", "snowflake": "NUMBER({p},{s})",   "bigquery": "NUMERIC({p},{s})", "azure_synapse": "DECIMAL({p},{s})", "redshift": "DECIMAL({p},{s})", "mysql": "DECIMAL(38,10)", "mssql": "DECIMAL({p},{s})"},
    "FLOAT8":        {"postgres": "DOUBLE PRECISION", "snowflake": "FLOAT",             "bigquery": "FLOAT64",        "azure_synapse": "FLOAT",           "redshift": "DOUBLE PRECISION", "mysql": "DOUBLE",         "mssql": "FLOAT"},
    "FLOAT4":        {"postgres": "REAL",             "snowflake": "FLOAT",             "bigquery": "FLOAT64",        "azure_synapse": "REAL",            "redshift": "REAL",            "mysql": "FLOAT",          "mssql": "REAL"},
    "TEXT":          {"postgres": "VARCHAR({n})",     "snowflake": "VARCHAR({n})",      "bigquery": "STRING",         "azure_synapse": "VARCHAR({n})",    "redshift": "VARCHAR({n})",    "mysql": "VARCHAR({n})",   "mssql": "VARCHAR({n})"},
    "NTEXT":         {"postgres": "VARCHAR({n})",     "snowflake": "VARCHAR({n})",      "bigquery": "STRING",         "azure_synapse": "NVARCHAR({n})",   "redshift": "VARCHAR({n})",    "mysql": "VARCHAR({n})",   "mssql": "NVARCHAR({n})"},
    "CHAR":          {"postgres": "CHAR({n})",        "snowflake": "CHAR({n})",         "bigquery": "STRING",         "azure_synapse": "CHAR({n})",       "redshift": "CHAR({n})",       "mysql": "CHAR({n})",      "mssql": "CHAR({n})"},
    "DATE":          {"postgres": "DATE",             "snowflake": "DATE",              "bigquery": "DATE",           "azure_synapse": "DATE",            "redshift": "DATE",            "mysql": "DATE",           "mssql": "DATE"},
    "DATETIME":      {"postgres": "TIMESTAMP WITHOUT TIME ZONE", "snowflake": "TIMESTAMP_NTZ", "bigquery": "DATETIME",  "azure_synapse": "DATETIME2",   "redshift": "TIMESTAMP",       "mysql": "DATETIME(6)",    "mssql": "DATETIME2"},
    "DATETIMETZ":    {"postgres": "TIMESTAMPTZ",      "snowflake": "TIMESTAMP_TZ",      "bigquery": "TIMESTAMP",      "azure_synapse": "DATETIMEOFFSET",  "redshift": "TIMESTAMPTZ",     "mysql": "TIMESTAMP",      "mssql": "DATETIMEOFFSET"},
    "BOOL":          {"postgres": "BOOLEAN",          "snowflake": "BOOLEAN",           "bigquery": "BOOL",           "azure_synapse": "BIT",             "redshift": "BOOLEAN",         "mysql": "TINYINT(1)",     "mssql": "BIT"},
    "BYTES":         {"postgres": "BYTEA",            "snowflake": "BINARY({n})",       "bigquery": "BYTES",          "azure_synapse": "BINARY({n})",     "redshift": "VARCHAR({n})",    "mysql": "BINARY({n})",    "mssql": "BINARY({n})"},
    "VARBYTES":      {"postgres": "BYTEA",            "snowflake": "VARBINARY({n})",    "bigquery": "BYTES",          "azure_synapse": "VARBINARY({n})",  "redshift": "VARCHAR({n})",    "mysql": "VARBINARY({n})", "mssql": "VARBINARY({n})"},
    "CLOB":          {"postgres": "TEXT",             "snowflake": "VARCHAR(16777216)",  "bigquery": "STRING",         "azure_synapse": "NVARCHAR(MAX)",   "redshift": "VARCHAR(65535)",  "mysql": "LONGTEXT",       "mssql": "NVARCHAR(MAX)"},
    "BLOB":          {"postgres": "BYTEA",            "snowflake": "BINARY",            "bigquery": "BYTES",          "azure_synapse": "VARBINARY(MAX)",  "redshift": "VARCHAR(65535)",  "mysql": "LONGBLOB",       "mssql": "VARBINARY(MAX)"},
    "JSON":          {"postgres": "JSONB",            "snowflake": "VARIANT",           "bigquery": "JSON",           "azure_synapse": "NVARCHAR(MAX)",   "redshift": "SUPER",           "mysql": "JSON",           "mssql": "NVARCHAR(MAX)"},
    "XML":           {"postgres": "XML",              "snowflake": "VARCHAR(16777216)",  "bigquery": "STRING",         "azure_synapse": "XML",             "redshift": "VARCHAR(65535)",  "mysql": "LONGTEXT",       "mssql": "XML"},
}


def resolve_target_type(canonical: str, target_engine: str,
                        length: int | None = None,
                        precision: int | None = None,
                        scale: int | None = None) -> str:
    """Resolve a canonical type string (e.g. 'TEXT', 'DECIMAL') to the
    target engine's native type string, substituting {n}, {p}, {s}."""
    # Strip parameters from canonical key  e.g. "DECIMAL(18,2)" -> "DECIMAL"
    base = canonical.split("(")[0].upper()
    mapping = CANONICAL_TO_TARGET.get(base)
    if not mapping:
        raise ValueError(f"Unknown canonical type: {canonical}")
    template = mapping.get(target_engine)
    if not template:
        raise ValueError(f"No mapping for canonical {canonical} -> {target_engine}")
    n = length or 255
    p = precision or 38
    s = scale or 0
    return template.format(n=n, p=p, s=s)


# ---------------------------------------------------------------------------
# Source-engine native type -> Canonical type mapping helpers
# ---------------------------------------------------------------------------
MSSQL_TYPE_MAP: dict[str, str] = {
    "bigint":          "INT8",
    "int":             "INT4",
    "smallint":        "INT2",
    "tinyint":         "INT1",
    "decimal":         "DECIMAL",
    "numeric":         "DECIMAL",
    "money":           "DECIMAL",    # -> DECIMAL(19,4)
    "smallmoney":      "DECIMAL",    # -> DECIMAL(10,4)
    "float":           "FLOAT8",
    "real":            "FLOAT4",
    "varchar":         "TEXT",
    "nvarchar":        "NTEXT",
    "char":            "CHAR",
    "nchar":           "CHAR",
    "text":            "CLOB",
    "ntext":           "CLOB",
    "date":            "DATE",
    "datetime":        "DATETIME",
    "datetime2":       "DATETIME",
    "smalldatetime":   "DATETIME",
    "datetimeoffset":  "DATETIMETZ",
    "time":            "DATETIME",
    "bit":             "BOOL",
    "binary":          "BYTES",
    "varbinary":       "VARBYTES",
    "image":           "BLOB",
    "xml":             "XML",
    "uniqueidentifier": "TEXT",      # UUID -> TEXT(36)
}

POSTGRES_SOURCE_TYPE_MAP: dict[str, str] = {
    "bigint":              "INT8",
    "integer":             "INT4",
    "smallint":            "INT2",
    "serial":              "INT4",
    "bigserial":           "INT8",
    "numeric":             "DECIMAL",
    "double precision":    "FLOAT8",
    "real":                "FLOAT4",
    "character varying":   "TEXT",
    "varchar":             "TEXT",
    "character":           "CHAR",
    "char":                "CHAR",
    "text":                "CLOB",
    "date":                "DATE",
    "timestamp without time zone": "DATETIME",
    "timestamp with time zone":    "DATETIMETZ",
    "boolean":             "BOOL",
    "bytea":               "BLOB",
    "json":                "JSON",
    "jsonb":               "JSON",
    "xml":                 "XML",
    "uuid":                "TEXT",
    "inet":                "TEXT",
    "cidr":                "TEXT",
    "macaddr":             "TEXT",
    "interval":            "TEXT",
    "money":               "DECIMAL",
}


# ===================================================================
# Abstract Base Classes
# ===================================================================

class SourceConnector(ABC):
    """Abstract interface that every source-engine connector must implement.

    The pipeline core calls only these methods — it never writes
    engine-specific SQL directly.
    """

    engine_name: str = "unknown"

    @abstractmethod
    def connect(self, config: dict) -> None:
        """Establish connection using engine-specific credentials.

        Raises:
            ConnectionError: If the connection cannot be established.
        """

    @abstractmethod
    def list_tables(self, database: str, schemas: list[str]) -> list[dict]:
        """Return list of ``{schema, name, table_kind, comment}``."""

    @abstractmethod
    def get_columns(self, database: str, schema: str, table: str) -> list[dict]:
        """Return list of column defs::

            {name, source_type_raw, canonical_type, length, precision,
             scale, nullable, default, column_id, comment, charset}
        """

    @abstractmethod
    def get_primary_keys(self, database: str, schema: str, table: str) -> dict:
        """Return ``{columns: [...], type: 'pk'}``."""

    @abstractmethod
    def get_foreign_keys(self, database: str, schema: str, table: str) -> list[dict]:
        """Return list of FK defs including parent table and columns."""

    @abstractmethod
    def get_indexes(self, database: str, schema: str, table: str) -> list[dict]:
        """Return non-PK index definitions."""

    @abstractmethod
    def get_raw_ddl(self, database: str, schema: str, table: str) -> str | None:
        """Return raw DDL string if the source supports it, else ``None``."""

    @abstractmethod
    def get_column_stats(self, database: str, schema: str, table: str,
                         columns: list[str], sample: int) -> dict:
        """Return ``{col: {null_rate, distinct_count, min, max, max_len}}``."""

    @abstractmethod
    def extract_chunk(self, database: str, schema: str, table: str,
                      columns: list[dict],
                      where_clause: str | None,
                      pk_col: str, start: int, end: int) -> list[dict]:
        """Extract one chunk of rows between *start* and *end* PK values."""

    @abstractmethod
    def run_aggregate(self, database: str, schema: str, table: str,
                      column: str, func: str) -> Any:
        """Run SUM / MIN / MAX / COUNT_DISTINCT on a source column.

        *func* is one of ``SUM``, ``MIN``, ``MAX``, ``COUNT_DISTINCT``.
        Uses ``COALESCE(..., 0)`` for SUM to normalise NULL-only columns.
        """

    @abstractmethod
    def get_row_count(self, database: str, schema: str, table: str) -> int:
        """Return total row count for a source table."""

    def close(self) -> None:
        """Close the connection (optional override)."""
        pass


class TargetConnector(ABC):
    """Abstract interface that every target-engine connector must implement."""

    engine_name: str = "unknown"

    @abstractmethod
    def connect(self, config: dict) -> None:
        """Establish connection using engine-specific credentials.

        Raises:
            ConnectionError: If the connection cannot be established.
        """

    @abstractmethod
    def render_create_table(self, mapping: dict, schema: str) -> str:
        """Render a ``CREATE TABLE`` SQL string from an approved mapping dict."""

    @abstractmethod
    def render_indexes(self, mapping: dict, schema: str) -> list[str]:
        """Render index ``CREATE`` statements from mapping."""

    @abstractmethod
    def apply_ddl(self, sql: str) -> None:
        """Execute DDL on the target.  Idempotent (``CREATE IF NOT EXISTS``)."""

    @abstractmethod
    def bulk_load(self, target_table: str,
                  columns: list[str], rows: list[dict]) -> int:
        """Load a batch of rows.  Returns number successfully loaded."""

    @abstractmethod
    def get_row_count(self, table: str) -> int:
        """Return row count for validation."""

    @abstractmethod
    def run_aggregate(self, table: str, column: str, func: str) -> Any:
        """Run SUM / MIN / MAX / COUNT(DISTINCT) on target column."""

    @abstractmethod
    def disable_fk_constraints(self, table: str) -> None:
        """Disable FK constraints for bulk loading."""

    @abstractmethod
    def enable_fk_constraints(self, table: str) -> None:
        """Re-enable FK constraints after bulk loading."""

    def close(self) -> None:
        """Close the connection (optional override)."""
        pass
