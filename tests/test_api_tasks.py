import io
import time

import pandas as pd
import pytest
from fastapi.testclient import TestClient

import agent.nodes.plan as plan_nodes
import executors

PLAN = {
    "goal": "各渠道销售额",
    "metrics": ["sales_amount"],
    "dimensions": ["channel"],
    "filters": {},
    "time_range": "",
    "tool": "pandas",
    "needs_chart": True,
    "chart_type": "bar",
    "reason": "",
}


class FakeExecutor:
    """最小执行器：generate 返回代码，execute 按 approved 决定成败。"""

    name = "pandas"

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
        if artifact.get("approval_required", False) and not artifact.get("approved", False):
            return {"rows": [], "summary": {}, "error": "Code execution not approved.", "terminal": True}
        df = pd.DataFrame({"channel": ["线上"], "sales_amount": [1.0]})
        return {"rows": df.to_dict(orient="records"), "summary": {}, "error": "", "terminal": False}


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(plan_nodes, "invoke_json", lambda *a, **k: dict(PLAN))

    executors.init_executors()
    executors.register_executor(FakeExecutor())

    from server.main import app

    with TestClient(app) as c:
        yield c

    executors.registry._EXECUTOR_REGISTRY.clear()


def _wait_terminal(client, task_id, timeout=20):
    for _ in range(timeout * 10):
        resp = client.get(f"/api/tasks/{task_id}")
        assert resp.status_code == 200
        view = resp.json()
        if view["status"] in ("awaiting_approval", "completed", "failed"):
            return view
        time.sleep(0.1)
    raise AssertionError("task did not reach terminal state")


def _upload(client):
    csv = b"channel,sales_amount\nA,10\nB,20\n"
    resp = client.post("/api/files", files={"file": ("demo.csv", io.BytesIO(csv), "text/csv")})
    assert resp.status_code == 200
    return resp.json()


def test_health(client):
    assert client.get("/api/health").json() == {"status": "ok"}


def test_upload_returns_file_id(client):
    body = _upload(client)
    assert body["file_id"] and body["source_type"] == "csv"


def test_task_reaches_awaiting_approval(client):
    body = _upload(client)
    resp = client.post("/api/tasks", json={"file_id": body["file_id"], "question": "各渠道销售额"})
    assert resp.status_code == 200
    view = _wait_terminal(client, resp.json()["task_id"])
    assert view["status"] == "awaiting_approval"
    assert view["approval"] is not None
    assert view["approval"]["language"] == "python"


def test_approve_completes(client):
    body = _upload(client)
    task_id = client.post(
        "/api/tasks", json={"file_id": body["file_id"], "question": "各渠道销售额"}
    ).json()["task_id"]
    _wait_terminal(client, task_id)

    resp = client.post(f"/api/tasks/{task_id}/resume", json={"approved": True})
    assert resp.status_code == 200
    view = _wait_terminal(client, task_id)
    assert view["status"] == "completed"
    assert view["rows"] and view["report"]


def test_reject_terminates(client):
    body = _upload(client)
    task_id = client.post(
        "/api/tasks", json={"file_id": body["file_id"], "question": "各渠道销售额"}
    ).json()["task_id"]
    _wait_terminal(client, task_id)

    client.post(f"/api/tasks/{task_id}/resume", json={"approved": False})
    view = _wait_terminal(client, task_id)
    assert view["status"] == "failed"
    assert view["approval"] is None
    assert "not approved" in view["error"].lower()


def test_unknown_task_returns_404(client):
    assert client.get("/api/tasks/does-not-exist").status_code == 404


def test_task_with_unknown_file_returns_404(client):
    resp = client.post("/api/tasks", json={"file_id": "nope", "question": "x"})
    assert resp.status_code == 404


def test_delete_cleans_temp_file(client):
    import os

    import server.api.tasks as tasks_api

    body = _upload(client)
    task_id = client.post(
        "/api/tasks", json={"file_id": body["file_id"], "question": "各渠道销售额"}
    ).json()["task_id"]
    _wait_terminal(client, task_id)

    record = tasks_api.STORE.get(task_id)
    assert os.path.exists(record.file_path)

    assert client.delete(f"/api/tasks/{task_id}").status_code == 200
    assert not os.path.exists(record.file_path)


def test_delete_unknown_task_returns_404(client):
    assert client.delete("/api/tasks/nope").status_code == 404


def test_resume_when_not_awaiting_returns_409(client):
    body = _upload(client)
    task_id = client.post(
        "/api/tasks", json={"file_id": body["file_id"], "question": "各渠道销售额"}
    ).json()["task_id"]
    _wait_terminal(client, task_id)

    client.post(f"/api/tasks/{task_id}/resume", json={"approved": False})
    view = _wait_terminal(client, task_id)
    assert view["status"] == "failed"

    resp = client.post(f"/api/tasks/{task_id}/resume", json={"approved": True})
    assert resp.status_code == 409


def test_events_unknown_task_returns_404(client):
    assert client.get("/api/tasks/does-not-exist/events").status_code == 404


def test_events_streams_completed_snapshot(client):
    from server.api.tasks import STORE, TaskRecord
    from service import RunResult

    task_id = "sse-completed"
    STORE.set(TaskRecord(
        task_id=task_id,
        thread_id="t",
        status="completed",
        result=RunResult(thread_id="t", status="completed", report="done"),
    ))
    resp = client.get(f"/api/tasks/{task_id}/events")
    assert resp.status_code == 200
    assert "text/event-stream" in resp.headers["content-type"]
    assert '"status": "completed"' in resp.text


def test_service_exception_marks_failed_without_stale_data(client, monkeypatch):
    import server.api.tasks as tasks_api

    def boom(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(tasks_api.SERVICE, "start_analysis", boom)

    body = _upload(client)
    task_id = client.post(
        "/api/tasks", json={"file_id": body["file_id"], "question": "各渠道销售额"}
    ).json()["task_id"]

    view = _wait_terminal(client, task_id)
    assert view["status"] == "failed"
    assert view["error"] == "boom"
    assert view["rows"] == [] and view["approval"] is None


def _wait_status(client, task_id, statuses, timeout=20):
    for _ in range(timeout * 10):
        resp = client.get(f"/api/tasks/{task_id}")
        assert resp.status_code == 200
        view = resp.json()
        if view["status"] in statuses:
            return view
        time.sleep(0.1)
    raise AssertionError(f"task did not reach one of {statuses}")


def test_cancel_running_task_stops_execution(client, monkeypatch):
    import agent.cancellation as cancellation_mod

    # 让 generate 阶段变成「耗时且可被取消」，以便任务停留在 running 态
    def slow_generate(self, state):
        event = cancellation_mod.current_cancel_event()
        for _ in range(100):
            if event is not None and event.is_set():
                raise cancellation_mod.CancellationError("任务已取消")
            time.sleep(0.05)
        return {"code": "result_df = df.head(2)", "kind": "pandas", "error": ""}

    monkeypatch.setattr(FakeExecutor, "generate", slow_generate)

    body = _upload(client)
    task_id = client.post(
        "/api/tasks", json={"file_id": body["file_id"], "question": "各渠道销售额"}
    ).json()["task_id"]

    # 任务仍在 running 时立即取消
    resp = client.delete(f"/api/tasks/{task_id}")
    assert resp.status_code == 200
    assert resp.json().get("cancelled") is True

    view = _wait_status(client, task_id, ("cancelled", "failed", "completed"))
    # 取消应在当前步骤后真正生效：状态回到 cancelled，而非跑完 completed
    assert view["status"] == "cancelled"
    # 记录保留（取消语义不是删除），再次 DELETE 才彻底清理
    assert client.get(f"/api/tasks/{task_id}").status_code == 200
    assert client.delete(f"/api/tasks/{task_id}").status_code == 200
    assert client.get(f"/api/tasks/{task_id}").status_code == 404


def test_delete_on_terminal_task_still_cleans(client):
    """终态任务（非 running）的 DELETE 保持原语义：彻底删除并清理临时文件。"""
    import os

    import server.api.tasks as tasks_api

    body = _upload(client)
    task_id = client.post(
        "/api/tasks", json={"file_id": body["file_id"], "question": "各渠道销售额"}
    ).json()["task_id"]
    _wait_terminal(client, task_id)

    record = tasks_api.STORE.get(task_id)
    assert os.path.exists(record.file_path)

    assert client.delete(f"/api/tasks/{task_id}").status_code == 200
    assert not os.path.exists(record.file_path)


def test_apply_cancel_precedence_overrides_completed():
    """取消优先：即便 worker 跑出 completed，已置位的 cancel_event 也保持 cancelled。"""
    import threading

    import server.api.tasks as tasks_api
    from server.task_store import TaskRecord
    from service import RunResult

    record = TaskRecord(
        task_id="prec",
        thread_id="",
        status="completed",
        result=RunResult(thread_id="t", status="completed", report="r"),
    )
    record.cancel_event = threading.Event()
    record.cancel_event.set()

    tasks_api._apply_cancel_precedence(record)

    assert record.status == "cancelled"
    assert record.result is None


def test_apply_cancel_precedence_noop_when_not_cancelled():
    """未取消时不应篡改终态。"""
    import server.api.tasks as tasks_api
    from server.task_store import TaskRecord
    from service import RunResult

    record = TaskRecord(
        task_id="prec2",
        thread_id="",
        status="completed",
        result=RunResult(thread_id="t", status="completed", report="r"),
    )
    record.cancel_event = None

    tasks_api._apply_cancel_precedence(record)

    assert record.status == "completed"
    assert record.result is not None
