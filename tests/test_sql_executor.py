"""SQL 执行器测试：重点回归「连接不能跨线程」的取消包装问题。"""
import sqlite3

import pytest

from agent.prompts import SQL_GENERATOR_PROMPT, SQL_REPAIR_PROMPT
from executors.sql_executor import SQLExecutor


def _make() -> SQLExecutor:
    return SQLExecutor(
        generator_prompt=SQL_GENERATOR_PROMPT,
        repair_prompt=SQL_REPAIR_PROMPT,
        artifact_kind="sql",
    )


def _seed(db_path: str) -> None:
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE sales(channel TEXT, sales INTEGER)")
    conn.executemany("INSERT INTO sales VALUES (?,?)", [("A", 10), ("B", 20)])
    conn.commit()
    conn.close()


def test_execute_runs_in_same_thread_no_cross_thread_error(tmp_path):
    # 回归：execute 经 run_blocking_with_cancel 把查询放进守护线程，连接必须在该
    # 线程内创建并使用，否则会触发 sqlite3.ProgrammingError（SQLite objects created
    # in a thread can only be used in the same thread）。
    db = tmp_path / "t.db"
    _seed(str(db))
    ex = _make()
    state = {
        "input": {"data_source_type": "sqlite", "file_path": str(db)},
        "artifact": {
            "code": "SELECT channel, SUM(sales) AS s FROM sales GROUP BY channel ORDER BY s DESC",
            "approved": True,
        },
    }
    res = ex.execute(state)
    assert res["error"] == "", res["error"]
    assert len(res["rows"]) == 2
    assert res["rows"][0]["channel"] == "B"
    assert res["rows"][0]["s"] == 20


def test_execute_rejects_when_not_approved():
    ex = _make()
    state = {
        "input": {"data_source_type": "sqlite", "file_path": "x.db"},
        "artifact": {"code": "SELECT 1", "approved": False},
    }
    res = ex.execute(state)
    assert res["terminal"] is True


def test_execute_propagates_cancellation(monkeypatch, tmp_path):
    # 取消信号必须上浮为 CancellationError，绝不能变成普通错误返回（否则会落入
    # 修复循环而非真正停止任务）。
    from agent.cancellation import CancellationError

    db = tmp_path / "t.db"
    _seed(str(db))

    def _boom(conn, sql):
        raise CancellationError("任务已取消")

    monkeypatch.setattr("executors.sql_executor.run_sql", _boom)

    ex = _make()
    state = {
        "input": {"data_source_type": "sqlite", "file_path": str(db)},
        "artifact": {"code": "SELECT 1", "approved": True},
    }
    with pytest.raises(CancellationError):
        ex.execute(state)
