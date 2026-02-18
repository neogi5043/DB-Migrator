"""SQL Server (MSSQL) source connector — pyodbc driver."""
from __future__ import annotations
import logging
from typing import Any
from src.connectors.base import SourceConnector, MSSQL_TYPE_MAP

log = logging.getLogger(__name__)


class MSSQLSourceConnector(SourceConnector):
    engine_name = "mssql"

    def __init__(self):
        self.conn = None

    def connect(self, config: dict) -> None:
        try:
            import pyodbc
            ms = config["mssql"]
            conn_str = (
                f"DRIVER={{ODBC Driver 18 for SQL Server}};"
                f"SERVER={ms['host']},{ms.get('port', 1433)};"
                f"DATABASE={ms.get('database', '')};"
                f"UID={ms['user']};PWD={ms['password']};"
                f"TrustServerCertificate=yes"
            )
            self.conn = pyodbc.connect(conn_str)
            log.info("Connected to SQL Server at %s:%s", ms["host"], ms.get("port", 1433))
        except Exception as exc:
            raise ConnectionError(f"mssql: {exc}") from exc

    def list_tables(self, database: str, schemas: list[str]) -> list[dict]:
        schema_filter = ""
        params: list = []
        if schemas:
            placeholders = ",".join(["?"] * len(schemas))
            schema_filter = f"AND t.TABLE_SCHEMA IN ({placeholders})"
            params = list(schemas)

        sql = f"""
            SELECT t.TABLE_SCHEMA, t.TABLE_NAME, t.TABLE_TYPE
            FROM INFORMATION_SCHEMA.TABLES t
            WHERE t.TABLE_CATALOG = ? AND t.TABLE_TYPE = 'BASE TABLE'
            {schema_filter}
            ORDER BY t.TABLE_NAME
        """
        cur = self.conn.cursor()
        cur.execute(sql, [database] + params)
        return [{"schema": r[0], "name": r[1], "table_kind": "T",
                 "comment": ""} for r in cur.fetchall()]

    def get_columns(self, database: str, schema: str, table: str) -> list[dict]:
        sql = """
            SELECT c.COLUMN_NAME, c.DATA_TYPE, c.CHARACTER_MAXIMUM_LENGTH,
                   c.NUMERIC_PRECISION, c.NUMERIC_SCALE,
                   c.IS_NULLABLE, c.COLUMN_DEFAULT, c.ORDINAL_POSITION,
                   c.COLLATION_NAME,
                   COLUMNPROPERTY(OBJECT_ID(c.TABLE_SCHEMA + '.' + c.TABLE_NAME),
                                  c.COLUMN_NAME, 'IsIdentity') AS is_identity,
                   COLUMNPROPERTY(OBJECT_ID(c.TABLE_SCHEMA + '.' + c.TABLE_NAME),
                                  c.COLUMN_NAME, 'IsComputed') AS is_computed
            FROM INFORMATION_SCHEMA.COLUMNS c
            WHERE c.TABLE_CATALOG = ? AND c.TABLE_SCHEMA = ? AND c.TABLE_NAME = ?
            ORDER BY c.ORDINAL_POSITION
        """
        cur = self.conn.cursor()
        cur.execute(sql, [database, schema, table])
        cols = []
        for r in cur.fetchall():
            raw = r[1].lower()
            canonical = MSSQL_TYPE_MAP.get(raw, "TEXT")
            precision, scale = r[3], r[4]
            length = r[2]

            # MONEY / SMALLMONEY special handling
            if raw == "money":
                precision, scale = 19, 4
            elif raw == "smallmoney":
                precision, scale = 10, 4

            # BIT -> BOOL
            if raw == "bit":
                canonical = "BOOL"

            comments = []
            if r[9] == 1:
                comments.append("IDENTITY")
            if r[10] == 1:
                comments.append("COMPUTED")

            cols.append({
                "name": r[0], "source_type_raw": r[1],
                "canonical_type": canonical,
                "length": length, "precision": precision, "scale": scale,
                "nullable": r[5] == "YES",
                "default": r[6],
                "column_id": r[7],
                "comment": "; ".join(comments),
                "charset": r[8],
            })
        return cols

    def get_primary_keys(self, database: str, schema: str, table: str) -> dict:
        sql = """
            SELECT cu.COLUMN_NAME
            FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS tc
            JOIN INFORMATION_SCHEMA.CONSTRAINT_COLUMN_USAGE cu
              ON tc.CONSTRAINT_NAME = cu.CONSTRAINT_NAME
            WHERE tc.TABLE_CATALOG = ? AND tc.TABLE_SCHEMA = ?
              AND tc.TABLE_NAME = ? AND tc.CONSTRAINT_TYPE = 'PRIMARY KEY'
        """
        cur = self.conn.cursor()
        cur.execute(sql, [database, schema, table])
        return {"columns": [r[0] for r in cur.fetchall()], "type": "pk"}

    def get_foreign_keys(self, database: str, schema: str, table: str) -> list[dict]:
        sql = """
            SELECT
                COL_NAME(fkc.parent_object_id, fkc.parent_column_id) AS col,
                OBJECT_SCHEMA_NAME(fk.referenced_object_id) AS ref_schema,
                OBJECT_NAME(fk.referenced_object_id) AS ref_table,
                COL_NAME(fkc.referenced_object_id, fkc.referenced_column_id) AS ref_col
            FROM sys.foreign_keys fk
            JOIN sys.foreign_key_columns fkc ON fk.object_id = fkc.constraint_object_id
            WHERE OBJECT_SCHEMA_NAME(fk.parent_object_id) = ?
              AND OBJECT_NAME(fk.parent_object_id) = ?
        """
        cur = self.conn.cursor()
        cur.execute(sql, [schema, table])
        return [{"column": r[0], "parent_schema": r[1],
                 "parent_table": r[2], "parent_column": r[3]}
                for r in cur.fetchall()]

    def get_indexes(self, database: str, schema: str, table: str) -> list[dict]:
        sql = """
            SELECT i.name, ic.key_ordinal, COL_NAME(ic.object_id, ic.column_id),
                   i.is_unique
            FROM sys.indexes i
            JOIN sys.index_columns ic ON i.object_id = ic.object_id
              AND i.index_id = ic.index_id
            WHERE OBJECT_SCHEMA_NAME(i.object_id) = ?
              AND OBJECT_NAME(i.object_id) = ?
              AND i.is_primary_key = 0 AND i.type > 0
            ORDER BY i.name, ic.key_ordinal
        """
        cur = self.conn.cursor()
        cur.execute(sql, [schema, table])
        idx_map: dict[str, dict] = {}
        for r in cur.fetchall():
            name = r[0]
            if name not in idx_map:
                idx_map[name] = {"name": name, "unique": bool(r[3]),
                                 "columns": []}
            idx_map[name]["columns"].append(r[2])
        return list(idx_map.values())

    def get_raw_ddl(self, database: str, schema: str, table: str) -> str | None:
        return None  # MSSQL has no simple SHOW CREATE TABLE

    def get_column_stats(self, database: str, schema: str, table: str,
                         columns: list[str], sample: int) -> dict:
        stats: dict = {}
        cur = self.conn.cursor()
        for col in columns:
            sql = f"""
                SELECT TOP {sample}
                    SUM(CASE WHEN [{col}] IS NULL THEN 1.0 ELSE 0 END) / COUNT(*),
                    COUNT(DISTINCT [{col}]),
                    MIN([{col}]), MAX([{col}])
                FROM [{schema}].[{table}] WITH (NOLOCK)
            """
            try:
                cur.execute(sql)
                r = cur.fetchone()
                stats[col] = {"null_rate": float(r[0]) if r[0] else None,
                              "distinct_count": r[1],
                              "min": str(r[2]) if r[2] is not None else None,
                              "max": str(r[3]) if r[3] is not None else None}
            except Exception as e:
                log.warning("Stats failed for %s.%s: %s", table, col, e)
                stats[col] = {"null_rate": None, "distinct_count": None,
                              "min": None, "max": None}
        return stats

    def extract_chunk(self, database: str, schema: str, table: str,
                      columns: list[dict], where_clause: str | None,
                      pk_col: str | None, offset: int, limit: int) -> list[dict]:
        """Extract a chunk of rows using OFFSET/FETCH NEXT."""
        col_names = [c.get("source", c.get("name")) for c in columns]
        select = ", ".join(f"[{n}]" for n in col_names)
        sql = f"SELECT {select} FROM [{schema}].[{table}] WITH (NOLOCK)"
        if where_clause:
            sql += f" WHERE ({where_clause})"
        sql += f" ORDER BY 1 OFFSET {offset} ROWS FETCH NEXT {limit} ROWS ONLY"
        cur = self.conn.cursor()
        cur.execute(sql)
        return [dict(zip(col_names, row)) for row in cur.fetchall()]

    def run_aggregate(self, database: str, schema: str, table: str,
                      column: str, func: str) -> Any:
        if func == "COUNT_DISTINCT":
            expr = f"COUNT(DISTINCT [{column}])"
        elif func == "SUM":
            expr = f"COALESCE(SUM([{column}]), 0)"
        else:
            expr = f"{func}([{column}])"
        sql = f"SELECT {expr} FROM [{schema}].[{table}] WITH (NOLOCK)"
        cur = self.conn.cursor()
        cur.execute(sql)
        return cur.fetchone()[0]

    def get_row_count(self, database: str, schema: str, table: str) -> int:
        cur = self.conn.cursor()
        cur.execute(f"SELECT COUNT_BIG(*) FROM [{schema}].[{table}] WITH (NOLOCK)")
        return cur.fetchone()[0]

    def close(self) -> None:
        if self.conn:
            self.conn.close()

    def list_routines(self, database: str, schema: str) -> list[dict]:
        return []  # Not implemented for MSSQL yet

    def get_routine_definition(self, database: str, schema: str, name: str) -> str:
        return ""

    def list_views(self, database: str, schema: str) -> list[dict]:
        return []

    def get_view_definition(self, database: str, schema: str, name: str) -> str:
        return ""

    def list_triggers(self, database: str, schema: str) -> list[dict]:
        return []

    def get_trigger_definition(self, database: str, schema: str, name: str, table: str) -> str:
        return ""
