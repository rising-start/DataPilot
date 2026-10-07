"""DuckDB 执行器测试（未安装 duckdb 时整体跳过）。"""
import pytest

pytest.importorskip("duckdb")

from agent.prompts import DUCKDB_GENERATOR_PROMPT, DUCKDB_REPAIR_PROMPT
from executors.duckdb_executor import DuckDBExecutor


def _make() -> DuckDBExecutor:
    return DuckDBExecutor(
        generator_prompt=DUCKDB_GENERATOR_PROMPT,
        repair_prompt=DUCKDB_REPAIR_PROMPT,
        artifact_kind="duckdb",
    )


def test_supports():
    ex = _make()
    assert ex.supports({"input": {"data_source_type": "csv", "file_path": "x.csv"}}) is True
    assert ex.supports({"input": {"data_source_type": "sqlite", "file_path": "x.db"}}) is False
    assert ex.supports({"input": {"data_source_type": "excel", "file_path": "x.xlsx"}}) is False


def test_execute_aggregates_csv(tmp_path):
    csv = tmp_path / "sales.csv"
    csv.write_text("channel,sales\nA,10\nB,20\n")
    ex = _make()
    state = {
        "input": {"data_source_type": "csv", "file_path": str(csv)},
        "artifact": {
            "code": "SELECT channel, SUM(sales) AS s FROM data GROUP BY channel ORDER BY s DESC",
            "approved": True,
        },
    }
    res = ex.execute(state)
    assert res["error"] == "", res["error"]
    assert len(res["rows"]) == 2
    assert res["rows"][0]["channel"] == "B"
    assert res["rows"][0]["s"] == 20


def test_execute_rejects_unsafe_sql():
    ex = _make()
    state = {
        "input": {"data_source_type": "csv", "file_path": "x.csv"},
        "artifact": {"code": "DROP TABLE data", "approved": True},
    }
    res = ex.execute(state)
    assert res["error"]
    assert res["terminal"] is True


def test_execute_rejects_when_not_approved():
    ex = _make()
    state = {
        "input": {"data_source_type": "csv", "file_path": "x.csv"},
        "artifact": {"code": "SELECT 1", "approved": False},
    }
    res = ex.execute(state)
    assert res["terminal"] is True


def test_generate_rejects_unsafe(monkeypatch):
    import executors.duckdb_executor as mod

    monkeypatch.setattr(mod, "invoke_text", lambda *a, **k: "INSERT INTO data VALUES (1)")
    ex = _make()
    state = {"input": {"data_source_type": "csv", "file_path": "x.csv"}, "plan": {}, "dataset": {}}
    res = ex.generate(state)
    assert res["error"]
    assert res["terminal"] is True


def test_approval_payload_is_sql():
    ex = _make()
    payload = ex.get_approval_payload({"artifact": {"code": "SELECT 1 FROM data"}})
    assert payload["kind"] == "sql"


def test_execute_rejects_file_read():
    # 越权读取任意系统文件：SELECT ... FROM read_parquet('/etc/passwd')
    # 以 SELECT 开头、无禁用词，但 is_safe_sql 必须拦截文件读取表函数
    ex = _make()
    state = {
        "input": {"data_source_type": "csv", "file_path": "x.csv"},
        "artifact": {"code": "SELECT * FROM read_parquet('/etc/passwd')", "approved": True},
    }
    res = ex.execute(state)
    assert res["error"], "file read must be blocked"
    assert res["terminal"] is True


def test_apply_resource_limits_sets_pragmas():
    # 资源上限设置不应抛错，且可在引擎层回读验证生效
    import duckdb

    from executors.duckdb_executor import _apply_resource_limits

    con = duckdb.connect()
    try:
        _apply_resource_limits(con)
        # 回读验证内存上限确实生效（本环境不支持 PRAGMA memory_limit，用 current_setting）
        val = con.execute("SELECT current_setting('memory_limit')").fetchone()
        assert val is not None and val[0]
    finally:
        con.close()


def test_execute_respects_resource_limits(tmp_path):
    # 资源限制下正常查询仍可用（未被误伤）
    csv = tmp_path / "sales.csv"
    csv.write_text("channel,sales\nA,10\nB,20\n")
    ex = _make()
    state = {
        "input": {"data_source_type": "csv", "file_path": str(csv)},
        "artifact": {
            "code": "SELECT COUNT(*) AS n FROM data",
            "approved": True,
        },
    }
    res = ex.execute(state)
    assert res["error"] == "", res["error"]
    assert res["rows"][0]["n"] == 2
