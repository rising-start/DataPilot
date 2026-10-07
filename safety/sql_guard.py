import re
import sqlite3

import pandas as pd

FORBIDDEN_SQL = ["insert", "update", "delete", "drop", "alter", "truncate"]


def clean_sql(sql: str) -> str:
    sql = sql.strip()

    fenced = re.search(r"```sql\s*(.*?)\s*```", sql, re.DOTALL | re.IGNORECASE)
    if fenced:
        return fenced.group(1).strip()

    fenced2 = re.search(r"```\s*(.*?)\s*```", sql, re.DOTALL)
    if fenced2:
        return fenced2.group(1).strip()

    lines = []
    for line in sql.splitlines():
        stripped = line.strip()
        if stripped.startswith("下面是"):
            continue
        if stripped.startswith("这是"):
            continue
        if stripped.startswith("SQL"):
            continue
        lines.append(line)

    return "\n".join(lines).strip()


def is_safe_sql(sql: str) -> tuple[bool, str]:
    sql = clean_sql(sql)
    normalized = sql.strip().lower()

    # 允许 SELECT 和 WITH
    if not (normalized.startswith("select") or normalized.startswith("with")):
        return False, "Only SELECT is allowed."

    for keyword in FORBIDDEN_SQL:
        if re.search(rf"\b{keyword}\b", normalized):
            return False, f"Forbidden keyword detected: {keyword}"

    # 禁止文件读取表函数（DuckDB 等引擎可借此读取任意系统文件）。
    # 普通列名（如 read_count）不含这些函数名，不会误伤。
    file_read_funcs = (
        "read_csv", "read_csv_auto", "read_parquet", "read_json",
        "read_json_auto", "read_excel", "read_blob",
    )
    if re.search(r"\b(" + "|".join(file_read_funcs) + r")\b", normalized):
        return False, "File read table functions are not allowed."

    return True, ""


def run_sql(conn: sqlite3.Connection, sql: str) -> pd.DataFrame:
    sql = clean_sql(sql)
    return pd.read_sql_query(sql, conn)