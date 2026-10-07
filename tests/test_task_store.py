from server.schemas import TaskView
from server.task_store import InMemoryTaskStore, TaskRecord


def test_store_roundtrip():
    store = InMemoryTaskStore()
    record = TaskRecord(task_id="t1", thread_id="th1", status="running")
    store.set(record)
    assert store.get("t1").task_id == "t1"
    assert store.get("missing") is None


def test_store_delete_and_list():
    store = InMemoryTaskStore()
    store.set(TaskRecord(task_id="a", thread_id="1", status="running"))
    store.set(TaskRecord(task_id="b", thread_id="2", status="completed"))
    assert len(store.list()) == 2
    store.delete("a")
    assert store.get("a") is None
    assert [r.task_id for r in store.list()] == ["b"]


def test_task_view_defaults():
    view = TaskView(task_id="t", thread_id="th", status="running")
    assert view.rows == [] and view.insights == [] and view.approval is None
    assert view.error == ""
