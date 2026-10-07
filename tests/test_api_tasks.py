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
