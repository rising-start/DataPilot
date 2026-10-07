"""EventHub 单元测试：验证线程→事件循环的跨线程信号桥接。"""
import asyncio

from server.event_hub import EventHub


def test_signal_sets_subscribed_event():
    hub = EventHub()

    async def scenario():
        hub.attach_loop(asyncio.get_running_loop())
        event = hub.subscribe("t1")
        hub.signal("t1")  # 经 loop.call_soon_threadsafe 调度到当前 loop
        await asyncio.sleep(0)  # 让 loop 处理一次回调
        return event

    event = asyncio.run(scenario())
    assert event.is_set()


def test_unsubscribe_stops_signal():
    hub = EventHub()

    async def scenario():
        hub.attach_loop(asyncio.get_running_loop())
        event = hub.subscribe("t1")
        hub.unsubscribe("t1", event)
        hub.signal("t1")
        await asyncio.sleep(0)
        return event

    event = asyncio.run(scenario())
    assert not event.is_set()


def test_signal_unknown_task_is_noop():
    hub = EventHub()
    # 无 loop、无订阅者：signal 不应抛错
    hub.signal("never")


def test_events_404_for_unknown_task():
    # 任务不存在时 SSE 端点应直接返回 404（不建立长连接）
    from fastapi.testclient import TestClient

    from server.main import app

    client = TestClient(app)
    resp = client.get("/api/tasks/does-not-exist/events")
    assert resp.status_code == 404


def test_sse_stream_pushes_updates_and_closes_on_terminal():
    """完整 SSE 流：连接即推快照，状态变更经 HUB.signal 推送，终态后关流。"""
    from fastapi.testclient import TestClient

    from server.api.tasks import HUB, STORE
    from server.main import app
    from server.task_store import TaskRecord

    task_id = "sse-stream-1"
    try:
        STORE.set(
            TaskRecord(
                task_id=task_id,
                thread_id="",
                file_id="x",
                status="running",
                file_path="",
            )
        )

        def producer() -> None:
            import time
            time.sleep(0.2)  # 给 SSE 连接建立 + 订阅留出时间
            rec = STORE.get(task_id)
            rec.status = "completed"
            STORE.set(rec)
            HUB.signal(task_id)

        import threading
        threading.Thread(target=producer, daemon=True).start()

        client = TestClient(app)
        frames: list[str] = []
        with client.stream("GET", f"/api/tasks/{task_id}/events") as resp:
            assert resp.status_code == 200
            for line in resp.iter_lines():
                if line:
                    frames.append(line)
                if len(frames) >= 2:  # 初始快照 + 终态推送
                    break

        assert len(frames) >= 2
        assert any("completed" in f for f in frames)
    finally:
        STORE.delete(task_id)
