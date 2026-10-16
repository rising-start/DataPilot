import sqlite3
from pathlib import Path

import pandas as pd


def _to_readonly_uri(file_path: str) -> str:
    
    return f"{Path(file_path).resolve().as_uri()}?mode=ro"


def get_sqlite_connection(file_path: str) -> sqlite3.Connection:
    
    return sqlite3.connect(_to_readonly_uri(file_path), uri=True)


def list_tables(conn: sqlite3.Connection) -> list[str]:
    sql = "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;"
    rows = conn.execute(sql).fetchall()
    return [r[0] for r in rows]


def get_table_schema(conn: sqlite3.Connection, table_name: str) -> list[dict]:
    if not _table_exists(conn, table_name):
        raise ValueError(f"Table not found: {table_name}")

    rows = conn.execute(f"PRAGMA table_info({_quote_identifier(table_name)})").fetchall()
    return [
        {
            "cid": r[0],
            "name": r[1],
            "type": r[2],
            "notnull": r[3],
            "default": r[4],
            "pk": r[5],
        }
        for r in rows
    ]


def preview_table(conn: sqlite3.Connection, table_name: str, limit: int = 5) -> pd.DataFrame:
    if not _table_exists(conn, table_name):
        raise ValueError(f"Table not found: {table_name}")

    return pd.read_sql_query(
        f"SELECT * FROM {_quote_identifier(table_name)} LIMIT {int(limit)}", conn
    )


def _table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    return table_name in list_tables(conn)


def _quote_identifier(name: str) -> str:
    return '"' + str(name).replace('"', '""') + '"'
