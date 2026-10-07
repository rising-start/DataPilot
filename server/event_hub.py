"""进程内事件总线：把线程池任务的状态变化通知到 SSE 协程。

任务在 `ThreadPoolExecutor` 中执行，状态变化发生在工作线程；SSE 端点
（`server/api/tasks.py`）运行在事件循环线程。二者通过 `asyncio.Event`
+ `loop.call_soon_threadsafe` 桥接，避免跨线程直接操作异步原语。
"""
import asyncio
from typing import Dict, Set


class EventHub:
    def __init__(self) -> None:
        # task_id -> 该任务的订阅者事件集合（通常一个 SSE 连接对应一个）
        self._events: Dict[str, Set[asyncio.Event]] = {}
        self._loop: asyncio.AbstractEventLoop | None = None

    def attach_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        # 每个 SSE 连接在事件循环线程发起，绑定到当前活跃 loop。
        # 无条件覆盖：单进程单 loop 下等价，且避免单例跨循环复用时
        # 仍指向已关闭 loop，导致后续 signal 抛 RuntimeError。
        self._loop = loop

    def subscribe(self, task_id: str) -> asyncio.Event:
        event = asyncio.Event()
        self._events.setdefault(task_id, set()).add(event)
        return event

    def unsubscribe(self, task_id: str, event: asyncio.Event) -> None:
        subscribers = self._events.get(task_id)
        if subscribers is not None:
            subscribers.discard(event)
            if not subscribers:
                self._events.pop(task_id, None)

    def signal(self, task_id: str) -> None:
        """通知某任务有状态更新（工作线程安全调用）。

        仅把"投递"动作调度回事件循环线程执行；所有对 `self._events`
        集合的读写都集中在 loop 线程，避免与协程中的 subscribe/unsubscribe
        跨线程并发修改原生 set/dict 造成的数据竞争
        （如 RuntimeError: Set changed size during iteration）。
        """
        if self._loop is None:
            return
        # 无订阅者时无需调度（create_task 等场景下前端尚未建立 SSE 连接）
        if not self._events.get(task_id):
            return
        try:
            self._loop.call_soon_threadsafe(self._deliver, task_id)
        except RuntimeError:
            # 关联的事件循环已关闭（如测试跨 loop 复用单例），丢弃本次信号
            pass

    def _deliver(self, task_id: str) -> None:
        """在事件循环线程中唤醒订阅者；勿跨线程调用。"""
        subscribers = self._events.get(task_id)
        if not subscribers:
            return
        for event in list(subscribers):
            event.set()


# 进程级单例：所有任务与 SSE 连接共享
HUB = EventHub()
