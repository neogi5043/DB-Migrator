"""MySQL target connector — mysql-connector-python driver."""
from __future__ import annotations
import logging
from typing import Any
from src.connectors.base import TargetConnector

log = logging.getLogger(__name__)


class MySQLTargetConnector(TargetConnector):
    engine_name = "mysql"

    def __init__(self):
        self.conn = None

    def connect(self, config: dict) -> None:
        try:
            import mysql.connector
            my = config["mysql"]
            self.conn = mysql.connector.connect(
                host=my["host"], port=int(my.get("port", 3306)),
                user=my["user"], password=my["password"],
                database=my.get("database", ""),
                charset="utf8mb4",
            )
            # Disable PK requirement so DDL works on managed MySQL servers
            cur = self.conn.cursor()
            cur.execute("SET sql_require_primary_key = 0")
            self.conn.commit()
            log.info("Connected to target MySQL at %s:%s", my["host"], my.get("port", 3306))
        except Exception as exc:
            raise ConnectionError(f"mysql target: {exc}") from exc

    def render_create_table(self, mapping: dict, schema: str) -> str:
        tbl = mapping["target_table"]
        lines = []
        pk_cols = []
        for col in mapping["columns"]:
            name = col["target"]
            dtype = col["target_type"]
            nullable = "" if col.get("nullable", True) else " NOT NULL"
            auto = " AUTO_INCREMENT" if col.get("auto_increment") else ""
            lines.append(f"    `{name}` {dtype}{nullable}{auto}")
            if col.get("role") == "primary_key":
                pk_cols.append(f"`{name}`")
        if pk_cols:
            lines.append(f"    PRIMARY KEY ({', '.join(pk_cols)})")
        cols_sql = ",\n".join(lines)
        engine = mapping.get("mysql_engine", "InnoDB")
        charset = mapping.get("mysql_charset", "utf8mb4")
        return (
            f"CREATE TABLE IF NOT EXISTS `{schema}`.`{tbl}` (\n"
            f"{cols_sql}\n) ENGINE={engine} DEFAULT CHARSET={charset};"
        )

    def render_indexes(self, mapping: dict, schema: str) -> list[str]:
        # Build a lookup of column target types so we can add prefix lengths
        _TEXT_TYPES = {"LONGTEXT", "MEDIUMTEXT", "TEXT", "TINYTEXT",
                       "LONGBLOB", "MEDIUMBLOB", "BLOB", "TINYBLOB",
                       "JSON"}
        col_types: dict[str, str] = {}
        for col in mapping.get("columns", []):
            col_types[col["target"]] = col.get("target_type", "").upper()

        # Group index entries by name — mappings may store one entry per column
        grouped: dict[str, dict] = {}
        for idx in mapping.get("indexes", []):
            name = idx.get("name", "")
            if not name:
                continue
            if name not in grouped:
                grouped[name] = {"columns": [], "unique": idx.get("unique", False)}
            if "columns" in idx:
                grouped[name]["columns"].extend(idx["columns"])
            elif "column" in idx:
                col = idx["column"]
                if col not in grouped[name]["columns"]:
                    grouped[name]["columns"].append(col)

        stmts = []
        tbl = mapping["target_table"]
        for name, info in grouped.items():
            if not info["columns"]:
                continue
            parts = []
            for c in info["columns"]:
                ctype = col_types.get(c, "")
                # MySQL requires a prefix length for TEXT/BLOB index keys
                if ctype in _TEXT_TYPES:
                    parts.append(f"`{c}`(64)")
                else:
                    parts.append(f"`{c}`")
            cols = ", ".join(parts)
            unique = "UNIQUE " if info.get("unique") else ""
            stmts.append(
                f"CREATE {unique}INDEX `{name}` ON `{schema}`.`{tbl}` ({cols});"
            )
        return stmts

    def apply_ddl(self, sql: str) -> None:
        import mysql.connector.errors as me
        cur = self.conn.cursor()
        try:
            cur.execute(sql)
            self.conn.commit()
            log.info("DDL applied: %.80s…", sql.replace("\n", " "))
        except me.DatabaseError as e:
            # 1061 = Duplicate key name, 1050 = Table already exists,
            # 1071 = Key too long, 1170 = BLOB/TEXT in key without length
            if e.errno in (1061, 1050, 1071, 1170):
                log.warning("Skipped (already exists): %.80s…", sql.replace("\n", " "))
                self.conn.rollback()
            else:
                raise

    def bulk_load(self, target_table: str,
                  columns: list[str], rows: list[dict]) -> int:
        if not rows:
            return 0
        cur = self.conn.cursor()
        cols = ", ".join(f"`{c}`" for c in columns)
        placeholders = ", ".join(["%s"] * len(columns))
        sql = f"INSERT INTO {target_table} ({cols}) VALUES ({placeholders})"
        batch = [tuple(row.get(c) for c in columns) for row in rows]
        cur.executemany(sql, batch)
        self.conn.commit()
        return len(rows)

    def get_row_count(self, table: str) -> int:
        cur = self.conn.cursor()
        cur.execute(f"SELECT COUNT(*) FROM {table}")
        return cur.fetchone()[0]

    def run_aggregate(self, table: str, column: str, func: str) -> Any:
        if func.upper() == "COUNT_DISTINCT":
            sql = f"SELECT COUNT(DISTINCT `{column}`) FROM {table}"
        else:
            sql = f"SELECT COALESCE({func}(`{column}`), 0) FROM {table}"
        cur = self.conn.cursor()
        cur.execute(sql)
        return cur.fetchone()[0]

    def disable_fk_constraints(self, table: str) -> None:
        self.conn.cursor().execute("SET FOREIGN_KEY_CHECKS = 0")
        self.conn.commit()

    def enable_fk_constraints(self, table: str) -> None:
        self.conn.cursor().execute("SET FOREIGN_KEY_CHECKS = 1")
        self.conn.commit()

    def close(self) -> None:
        if self.conn:
            self.conn.close()
