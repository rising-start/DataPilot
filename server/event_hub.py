"""进程内事件总线：把线程池任务的状态变化通知到 SSE 协程。

任务在 `ThreadPoolExecutor` 中执行，状态变化发生在工作线程；SSE 端点
（`server/api/tasks.py`）运行在事件循环线程。二者通过 `asyncio.Event`
+ `loop.call_soon_threadsafe` 桥接，避免跨线程直接操作异步原语。
"""
import asyncio


class EventHub:
    def __init__(self) -> None:
        
        self._events: dict[str, set[asyncio.Event]] = {}
        self._loop: asyncio.AbstractEventLoop | None = None

    def attach_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        
        
        
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
        
        if self._loop is None:
            return
        
        if not self._events.get(task_id):
            return
        try:
            self._loop.call_soon_threadsafe(self._deliver, task_id)
        except RuntimeError:
            
            pass

    def _deliver(self, task_id: str) -> None:
        
        subscribers = self._events.get(task_id)
        if not subscribers:
            return
        for event in list(subscribers):
            event.set()



HUB = EventHub()
