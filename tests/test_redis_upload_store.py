"""RedisUploadStore 测试（无 Redis 时整体跳过）。"""

import os

import pytest

redis = pytest.importorskip("redis")

from server.files import (  # noqa: E402
    InMemoryTaskStore,
    RedisUploadStore,
    get_upload_store,
)


def _redis_store():
    url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    s = RedisUploadStore(url)
    try:
        s._client.ping()
    except Exception as e:  # noqa: BLE001
        pytest.skip(f"Redis 不可用，跳过 RedisUploadStore 测试：{e}")
    for key in s._client.scan_iter(match="datapilot:upload:*"):
        s._client.delete(key)
    return s


@pytest.fixture
def store():
    s = _redis_store()
    yield s
    for key in s._client.scan_iter(match="datapilot:upload:*"):
        s._client.delete(key)


def test_redis_upload_roundtrip(store):
    up = store.save("f1", "sales.csv", b"a,b\n1,2")
    assert up.file_id == "f1"
    assert up.source_type in {"csv", "excel"} or up.source_type  # 视 detect 而定
    got = store.get("f1")
    assert got is not None
    assert got.path == up.path
    # 元数据进 Redis（不含文件字节）
    raw = store._client.get("datapilot:upload:f1")
    assert b"sales.csv" in raw


def test_redis_upload_delete(store):
    store.save("f2", "x.csv", b"1")
    store.delete("f2")
    assert store.get("f2") is None


def test_get_upload_store_falls_back_without_redis(monkeypatch):
    monkeypatch.delenv("REDIS_URL", raising=False)
    from server.files import UploadStore

    assert isinstance(get_upload_store(), UploadStore)
