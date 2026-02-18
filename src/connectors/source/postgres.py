"""PostgreSQL source connector — psycopg2 driver."""
from __future__ import annotations
import logging
from typing import Any
from src.connectors.base import SourceConnector, POSTGRES_SOURCE_TYPE_MAP

log = logging.getLogger(__name__)


class PostgresSourceConnector(SourceConnector):
    engine_name = "postgres"

    def __init__(self):
        self.conn = None

    def connect(self, config: dict) -> None:
        try:
            import psycopg2
            pg = config["postgres"]
            self.conn = psycopg2.connect(
                host=pg["host"], port=int(pg.get("port", 5432)),
                dbname=pg["database"], user=pg["user"], password=pg["password"],
            )
            self.conn.autocommit = True
            log.info("Connected to PostgreSQL at %s:%s", pg["host"], pg.get("port", 5432))
        except Exception as exc:
            raise ConnectionError(f"postgres: {exc}") from exc

    def list_tables(self, database: str, schemas: list[str]) -> list[dict]:
        schema_list = schemas if schemas else ["public"]
        placeholders = ",".join(["%s"] * len(schema_list))
        sql = f"""
            SELECT table_schema, table_name, table_type
            FROM information_schema.tables
            WHERE table_schema IN ({placeholders})
              AND table_type = 'BASE TABLE'
            ORDER BY table_name
        """
        cur = self.conn.cursor()
        cur.execute(sql, schema_list)
        return [{"schema": r[0], "name": r[1], "table_kind": "T",
                 "comment": ""} for r in cur.fetchall()]

    def get_columns(self, database: str, schema: str, table: str) -> list[dict]:
        sql = """
            SELECT c.column_name, c.data_type, c.udt_name,
                   c.character_maximum_length, c.numeric_precision,
                   c.numeric_scale, c.is_nullable, c.column_default,
                   c.ordinal_position
            FROM information_schema.columns c
            WHERE c.table_schema = %s AND c.table_name = %s
            ORDER BY c.ordinal_position
        """
        cur = self.conn.cursor()
        cur.execute(sql, [schema, table])
        cols = []
        for r in cur.fetchall():
            raw = r[1]  # data_type
            udt = r[2]  # udt_name (e.g. 'int4', 'varchar', 'jsonb')
            canonical = POSTGRES_SOURCE_TYPE_MAP.get(raw, "TEXT")

            # Refine with udt_name
            if udt == "jsonb":
                canonical = "JSON"
            elif udt == "json":
                canonical = "JSON"
            elif udt == "uuid":
                canonical = "TEXT"

            comments = []
            default = r[7]
            if default and ("nextval" in str(default) or "generated" in str(default).lower()):
                comments.append("SERIAL/IDENTITY")

            cols.append({
                "name": r[0], "source_type_raw": raw,
                "canonical_type": canonical,
                "length": r[3], "precision": r[4], "scale": r[5],
                "nullable": r[6] == "YES",
                "default": default,
                "column_id": r[8],
                "comment": "; ".join(comments),
                "charset": None,
            })
        return cols

    def get_primary_keys(self, database: str, schema: str, table: str) -> dict:
        sql = """
            SELECT kcu.column_name
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu
              ON tc.constraint_name = kcu.constraint_name
              AND tc.table_schema = kcu.table_schema
            WHERE tc.table_schema = %s AND tc.table_name = %s
              AND tc.constraint_type = 'PRIMARY KEY'
            ORDER BY kcu.ordinal_position
        """
        cur = self.conn.cursor()
        cur.execute(sql, [schema, table])
        return {"columns": [r[0] for r in cur.fetchall()], "type": "pk"}

    def get_foreign_keys(self, database: str, schema: str, table: str) -> list[dict]:
        sql = """
            SELECT kcu.column_name,
                   ccu.table_schema AS ref_schema,
                   ccu.table_name AS ref_table,
                   ccu.column_name AS ref_column
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu
              ON tc.constraint_name = kcu.constraint_name
              AND tc.table_schema = kcu.table_schema
            JOIN information_schema.constraint_column_usage ccu
              ON tc.constraint_name = ccu.constraint_name
            WHERE tc.table_schema = %s AND tc.table_name = %s
              AND tc.constraint_type = 'FOREIGN KEY'
        """
        cur = self.conn.cursor()
        cur.execute(sql, [schema, table])
        return [{"column": r[0], "parent_schema": r[1],
                 "parent_table": r[2], "parent_column": r[3]}
                for r in cur.fetchall()]

    def get_indexes(self, database: str, schema: str, table: str) -> list[dict]:
        sql = """
            SELECT i.relname AS index_name,
                   a.attname AS column_name,
                   ix.indisunique
            FROM pg_class t
            JOIN pg_index ix ON t.oid = ix.indrelid
            JOIN pg_class i ON i.oid = ix.indexrelid
            JOIN pg_attribute a ON a.attrelid = t.oid
              AND a.attnum = ANY(ix.indkey)
            JOIN pg_namespace n ON n.oid = t.relnamespace
            WHERE n.nspname = %s AND t.relname = %s
              AND NOT ix.indisprimary
            ORDER BY i.relname, a.attnum
        """
        cur = self.conn.cursor()
        cur.execute(sql, [schema, table])
        idx_map: dict[str, dict] = {}
        for r in cur.fetchall():
            name = r[0]
            if name not in idx_map:
                idx_map[name] = {"name": name, "unique": r[2],
                                 "columns": []}
            idx_map[name]["columns"].append(r[1])
        return list(idx_map.values())

    def get_raw_ddl(self, database: str, schema: str, table: str) -> str | None:
        return None  # Postgres has no single SHOW CREATE TABLE

    def get_column_stats(self, database: str, schema: str, table: str,
                         columns: list[str], sample: int) -> dict:
        stats: dict = {}
        cur = self.conn.cursor()
        for col in columns:
            # Cast boolean columns to int so MIN/MAX work
            col_expr = f'"{col}"::int'
            # Try the cast-safe version first; fall back to plain column
            sql = f"""
                SELECT
                    SUM(CASE WHEN "{col}" IS NULL THEN 1 ELSE 0 END)::float
                      / GREATEST(COUNT(*), 1),
                    COUNT(DISTINCT "{col}"),
                    MIN({col_expr})::text, MAX({col_expr})::text
                FROM "{schema}"."{table}"
                LIMIT {sample}
            """
            try:
                cur.execute(sql)
                r = cur.fetchone()
                stats[col] = {"null_rate": r[0], "distinct_count": r[1],
                              "min": r[2], "max": r[3]}
            except Exception:
                # Retry without bool cast (normal columns)
                self.conn.rollback()
                sql2 = f"""
                    SELECT
                        SUM(CASE WHEN "{col}" IS NULL THEN 1 ELSE 0 END)::float
                          / GREATEST(COUNT(*), 1),
                        COUNT(DISTINCT "{col}"),
                        MIN("{col}")::text, MAX("{col}")::text
                    FROM "{schema}"."{table}"
                    LIMIT {sample}
                """
                try:
                    cur.execute(sql2)
                    r = cur.fetchone()
                    stats[col] = {"null_rate": r[0], "distinct_count": r[1],
                                  "min": r[2], "max": r[3]}
                except Exception as e2:
                    self.conn.rollback()
                    log.warning("Stats failed for %s.%s: %s", table, col, e2)
                    stats[col] = {"null_rate": None, "distinct_count": None,
                                  "min": None, "max": None}
        return stats

    def extract_chunk(self, database: str, schema: str, table: str,
                      columns: list[dict], where_clause: str | None,
                      pk_col: str | None, offset: int, limit: int) -> list[dict]:
        """Extract a chunk of rows using OFFSET/LIMIT."""
        col_names = [c.get("source", c.get("name")) for c in columns]
        select = ", ".join(f'"{n}"' for n in col_names)
        sql = f'SELECT {select} FROM "{schema}"."{table}"'
        if where_clause:
            sql += f" WHERE ({where_clause})"
        sql += f" ORDER BY 1 LIMIT {limit} OFFSET {offset}"
        cur = self.conn.cursor()
        cur.execute(sql)
        rows = []
        for row in cur.fetchall():
            d = {}
            for i, val in enumerate(row):
                if isinstance(val, dict):
                    import json as _json
                    val = _json.dumps(val)
                d[col_names[i]] = val
            rows.append(d)
        return rows

    def run_aggregate(self, database: str, schema: str, table: str,
                      column: str, func: str) -> Any:
        if func == "COUNT_DISTINCT":
            expr = f'COUNT(DISTINCT "{column}")'
        elif func == "SUM":
            expr = f'COALESCE(SUM("{column}"), 0)'
        else:
            expr = f'{func}("{column}")'
        sql = f'SELECT {expr} FROM "{schema}"."{table}"'
        cur = self.conn.cursor()
        cur.execute(sql)
        return cur.fetchone()[0]

    def get_row_count(self, database: str, schema: str, table: str) -> int:
        cur = self.conn.cursor()
        cur.execute(f'SELECT COUNT(*) FROM "{schema}"."{table}"')
        return cur.fetchone()[0]

    def close(self) -> None:
        if self.conn:
            self.conn.close()

    def list_routines(self, database: str, schema: str) -> list[dict]:
        sql = """
            SELECT routine_schema, routine_name, routine_type
            FROM information_schema.routines
            WHERE routine_schema = %s
              AND routine_type IN ('FUNCTION', 'PROCEDURE')
            ORDER BY routine_name
        """
        cur = self.conn.cursor()
        cur.execute(sql, [schema])
        return [{"schema": r[0], "name": r[1], "type": r[2]}
                for r in cur.fetchall()]

    def get_routine_definition(self, database: str, schema: str, name: str) -> str:
        # pg_get_functiondef needs the OID. We query by name and schema.
        # This might fail for overloaded functions; we take the first match for now.
        sql = """
            SELECT pg_get_functiondef(p.oid)
            FROM pg_proc p
            JOIN pg_namespace n ON p.pronamespace = n.oid
            WHERE n.nspname = %s AND p.proname = %s
            LIMIT 1
        """
        cur = self.conn.cursor()
        cur.execute(sql, [schema, name])
        row = cur.fetchone()
        return row[0] if row else ""

    def list_views(self, database: str, schema: str) -> list[dict]:
        sql = """
            SELECT table_schema, table_name
            FROM information_schema.views
            WHERE table_schema = %s
            ORDER BY table_name
        """
        cur = self.conn.cursor()
        cur.execute(sql, [schema])
        return [{"schema": r[0], "name": r[1]} for r in cur.fetchall()]

    def get_view_definition(self, database: str, schema: str, name: str) -> str:
        sql = """
            SELECT definition
            FROM pg_views
            WHERE schemaname = %s AND viewname = %s
        """
        cur = self.conn.cursor()
        cur.execute(sql, [schema, name])
        row = cur.fetchone()
        return row[0] if row else ""

    def list_triggers(self, database: str, schema: str) -> list[dict]:
        sql = """
            SELECT trigger_schema, trigger_name, event_object_table
            FROM information_schema.triggers
            WHERE trigger_schema = %s
            ORDER BY trigger_name
        """
        cur = self.conn.cursor()
        cur.execute(sql, [schema])
        return [{"schema": r[0], "name": r[1],
                 "table": r[2]} for r in cur.fetchall()]

    def get_trigger_definition(self, database: str, schema: str, name: str, table: str) -> str:
        sql = """
            SELECT pg_get_triggerdef(t.oid)
            FROM pg_trigger t
            JOIN pg_class c ON t.tgrelid = c.oid
            JOIN pg_namespace n ON c.relnamespace = n.oid
            WHERE n.nspname = %s AND t.tgname = %s AND c.relname = %s
        """
        cur = self.conn.cursor()
        cur.execute(sql, [schema, name, table])
        row = cur.fetchone()
        return row[0] if row else ""
