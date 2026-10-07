import sqlite3

import pandas as pd
import pytest

from safety.sql_guard import clean_sql, is_safe_sql, run_sql


def test_select_allowed():
    assert is_safe_sql("SELECT * FROM t LIMIT 10") == (True, "")


def test_with_cte_allowed():
    ok, _ = is_safe_sql("WITH x AS (SELECT 1 AS a) SELECT * FROM x")
    assert ok


@pytest.mark.parametrize(
    "sql",
    [
        "DELETE FROM t",
        "UPDATE t SET a = 1",
        "DROP TABLE t",
        "WITH x AS (SELECT 1) DELETE FROM t",
    ],
)
def test_forbidden_statements_rejected(sql):
    ok, reason = is_safe_sql(sql)
    assert not ok and reason


def test_fenced_sql_is_unwrapped():
    assert clean_sql("```sql\nSELECT 1\n```") == "SELECT 1"


def test_run_sql_returns_dataframe(tmp_path):
    conn = sqlite3.connect(tmp_path / "t.sqlite")
    conn.execute("CREATE TABLE t (a INTEGER)")
    conn.execute("INSERT INTO t VALUES (1)")
    conn.commit()
    df = run_sql(conn, "SELECT * FROM t")
    conn.close()
    assert isinstance(df, pd.DataFrame) and len(df) == 1
