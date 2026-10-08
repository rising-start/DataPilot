"""RedisTaskStore 测试。

无 Redis 可用时整体跳过（不污染无依赖的 CI/本地环境）；有 Redis 时验证
序列化往返、cancel_event 不落盘、delete/list 与遗留 running 恢复。
"""

import os
import threading

import pytest

redis = pytest.importorskip("redis")

from server.task_store import (  # noqa: E402
    InMemoryTaskStore,
    RedisTaskStore,
    TaskRecord,
    get_task_store,
)
from service import PendingApproval, RunResult  # noqa: E402


def _redis_client():
    url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    client = redis.Redis.from_url(url)
    try:
        client.ping()
    except Exception as e:  # noqa: BLE001
        pytest.skip(f"Redis 不可用，跳过 RedisTaskStore 测试：{e}")
    # 用独立 DB 避免污染，清空前缀
    for key in client.scan_iter(match="datapilot:task:*"):
        client.delete(key)
    return client


@pytest.fixture
def store():
    client = _redis_client()
    s = RedisTaskStore(os.getenv("REDIS_URL", "redis://localhost:6379/0"))
    # 复用同一连接并清空
    for key in s._client.scan_iter(match="datapilot:task:*"):
        s._client.delete(key)
    yield s
    for key in s._client.scan_iter(match="datapilot:task:*"):
        s._client.delete(key)


def _sample_record(task_id="t1"):
    result = RunResult(
        thread_id="th",
        status="awaiting_approval",
        tool="pandas",
        plan={"goal": "g"},
        pending=PendingApproval(kind="pandas", title="审批", content="x=1", language="python"),
        artifact_code="x=1",
        rows=[{"a": 1}],
        chart_spec={"chart_type": "bar"},
        insights=["i"],
        report="r",
        trace=[{"stage": "load", "status": "ok"}],
        logs=["l"],
        memory={"focus_entities": {}},
    )
    rec = TaskRecord(task_id=task_id, thread_id="th", file_id="f1", status="awaiting_approval")
    rec.result = result
    rec.cancel_event = threading.Event()
    return rec


def test_redis_roundtrip_preserves_fields(store):
    rec = _sample_record()
    store.set(rec)
    got = store.get("t1")
    assert got is not None
    assert got.task_id == "t1"
    assert got.status == "awaiting_approval"
    assert got.result is not None
    assert got.result.pending is not None
    assert got.result.pending.content == "x=1"
    assert got.result.rows == [{"a": 1}]
    assert got.result.chart_spec == {"chart_type": "bar"}


def test_redis_cancel_event_not_persisted(store):
    rec = _sample_record()
    rec.cancel_event.set()
    store.set(rec)
    # 重新取出：cancel_event 不来自 Redis，应通过内存映射保留
    got = store.get("t1")
    assert got.cancel_event is not None
    assert got.cancel_event.is_set()

    # 但 Redis 里的 JSON 不应包含 cancel_event
    raw = store._client.get("datapilot:task:t1")
    assert b"cancel_event" not in raw


def test_redis_identity_preserved_for_race_check(store):
    rec = _sample_record()
    store.set(rec)
    # get 返回的是同一内存对象，满足 STORE.get(id) is record 的竞态校验语义
    assert store.get("t1") is rec


def test_redis_delete_and_list(store):
    store.set(_sample_record("a"))
    store.set(_sample_record("b"))
    assert len(store.list()) == 2
    store.delete("a")
    assert store.get("a") is None
    assert [r.task_id for r in store.list()] == ["b"]


def test_redis_recover_flips_stale_running(store):
    rec = TaskRecord(task_id="stale", thread_id="th", status="running")
    store.set(rec)
    assert store.recover() == 1
    got = store.get("stale")
    assert got.status == "failed"
    assert "重启" in got.error
    assert got.result is None


def test_get_task_store_falls_back_without_redis(monkeypatch):
    monkeypatch.delenv("REDIS_URL", raising=False)
    assert isinstance(get_task_store(), InMemoryTaskStore)


def test_redis_apply_remote_cancel_sets_local_event(store):
    # 模拟「本副本持有带 worker cancel_event 的活对象」
    rec = _sample_record("live")
    rec.cancel_event = threading.Event()
    store._cache["live"] = rec

    store._apply_remote_cancel("live")
    assert rec.cancel_event.is_set()


def test_redis_apply_remote_cancel_noop_without_local_record(store):
    # 本副本没有该任务的活对象时不应报错（worker 在别的副本）
    store._apply_remote_cancel("not-here")


def test_redis_publish_cancel_does_not_raise(store):
    # 发布到无人订阅的频道不应抛错
    store.publish_cancel("any-id")


def test_redis_start_subscriber_idempotent(store):
    store.start_cancel_subscriber()
    store.start_cancel_subscriber()  # 第二次应无副作用
    assert store._subscriber_started is True

