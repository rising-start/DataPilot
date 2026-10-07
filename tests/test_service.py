import pandas as pd
import pytest

import agent.nodes.plan as plan_nodes
import executors
from executors.base import BaseExecutor
from service import AnalysisService

PLAN = {
    "goal": "各地区销售额",
    "metrics": ["sales_amount"],
    "dimensions": ["region"],
    "filters": {},
    "time_range": "",
    "tool": "pandas",
    "needs_chart": True,
    "chart_type": "bar",
    "reason": "",
}


class FakeExecutor(BaseExecutor):
    name = "pandas"

    def __init__(self, fail=False, terminal=False):
        self.fail = fail
        self.terminal = terminal

    def supports(self, state):
        return True

    def generate(self, state):
        return {"code": "result_df = df.head(2)", "kind": "pandas", "error": ""}

    def repair(self, state):
        return {"code": "result_df = df.head(1)", "kind": "pandas", "error": "", "retry_count": 1}

    def needs_approval(self, state):
        return True

    def get_approval_payload(self, state):
        return {
            "kind": "pandas",
            "title": "代码执行审批",
            "content": state.get("artifact", {}).get("code", ""),
            "message": "ok?",
        }

    def execute(self, state):
        artifact = state.get("artifact", {}) or {}
        # 与真实 CodeExecutor 一致：需要审批但被拒绝 -> 终止性错误
        if artifact.get("approval_required", False) and not artifact.get("approved", False):
            return {
                "rows": [],
                "summary": {},
                "error": "Code execution not approved.",
                "terminal": True,
            }
        if self.fail:
            return {"rows": [], "summary": {}, "error": "boom", "terminal": self.terminal}
        df = pd.DataFrame({"region": ["华东"], "sales_amount": [1.0]})
        return {"rows": df.to_dict(orient="records"), "summary": {}, "error": "", "terminal": False}


@pytest.fixture
def csv_path(tmp_path):
    path = tmp_path / "demo.csv"
    pd.DataFrame({"region": ["华东", "华南"], "sales_amount": [10.0, 30.0]}).to_csv(path, index=False)
    return str(path)


@pytest.fixture(autouse=True)
def fake_llm(monkeypatch):
    monkeypatch.setattr(plan_nodes, "invoke_json", lambda *a, **k: dict(PLAN))


@pytest.fixture(autouse=True)
def clean_registry():
    executors.init_executors()
    yield
    executors.registry._EXECUTOR_REGISTRY.clear()


def _service(fail=False, terminal=False):
    # 顺序要紧：先建 service（内部 init_executors 注册真实执行器），再覆盖同名 "pandas"
    svc = AnalysisService()
    executors.register_executor(FakeExecutor(fail=fail, terminal=terminal))
    return svc


def test_start_returns_awaiting_approval(csv_path):
    result = _service().start_analysis(csv_path, "csv", "各region销售额")
    assert result.status == "awaiting_approval"
    assert result.pending is not None and result.pending.kind == "pandas"
    assert result.pending.language == "python"


def test_approve_runs_to_completion(csv_path):
    svc = _service()
    first = svc.start_analysis(csv_path, "csv", "各region销售额")
    second = svc.resume(first.thread_id, approved=True)
    assert second.status == "completed"
    assert second.rows and second.report


def test_reject_terminates_without_new_approval(csv_path):
    svc = _service()
    first = svc.start_analysis(csv_path, "csv", "各region销售额")
    assert first.status == "awaiting_approval"

    second = svc.resume(first.thread_id, approved=False)
    assert second.status == "failed"
    assert second.pending is None
    assert "not approved" in second.error.lower()


def test_retry_is_bounded_by_max_retries(csv_path):
    """执行失败可修复时，重试次数必须有上限（retry_count 落在 execution 分组）。"""
    svc = _service(fail=True, terminal=False)
    result = svc.start_analysis(csv_path, "csv", "各region销售额")

    for _ in range(6):
        if result.pending is None:
            break
        result = svc.resume(result.thread_id, approved=True)

    assert result.status == "failed"
    assert result.error == "boom"


def test_load_failure_stops_the_run(tmp_path):
    """加载失败不能被后续节点把 error 清零后继续跑完整流程。"""
    svc = _service()
    missing = str(tmp_path / "not_exists.csv")
    result = svc.start_analysis(missing, "csv", "各region销售额")
    assert result.status == "failed"
    assert result.error


def test_unsupported_source_is_reported_as_failure(csv_path):
    svc = _service()
    result = svc.start_analysis(csv_path, "parquet", "各region销售额")
    assert result.status == "failed"
    assert result.error


def test_each_start_uses_fresh_thread(csv_path):
    svc = _service()
    first = svc.start_analysis(csv_path, "csv", "问题1")
    second = svc.start_analysis(csv_path, "csv", "问题2")
    assert first.thread_id != second.thread_id
