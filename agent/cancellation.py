"""任务取消：让「正在跑」的分析能被真正中断。

机制（与 `agent/progress.py` 同构，都用进程内注册 + task_id 透传，
避免把不可序列化的对象塞进 LangGraph checkpoint）：

- 每个 worker 线程持有自己的 `threading.Event`（挂在 `TaskRecord.cancel_event` 上）。
- worker 通过 `cancel_context(event)` 把 event 绑到「线程局部变量」，
  这样节点、LLM 调用、子进程执行等深层调用都能凭 `current_cancel_event()` 拿到它，
  而无需把 event 写进可序列化的图状态。
- DELETE /api/tasks/{id} 在任务 running 时 `event.set()`，worker 在
  节点入口 / LLM 调用 / 子进程等待 处轮询，发现即抛出 `CancellationError`。
- `CancellationError` 是 `BaseException` 子类，可穿透节点里的 `except Exception`，
  直达 `server/api/tasks.py` 的 worker 终态处理，把状态置为 `cancelled`。
"""

import threading
from contextlib import contextmanager


class CancellationError(BaseException):
    """任务被取消：穿透节点的 try/except，直达 worker 终态处理。"""


_local = threading.local()


def current_cancel_event() -> "threading.Event | None":
    """返回当前 worker 线程绑定的取消事件（未绑定返回 None）。"""
    return getattr(_local, "cancel_event", None)


@contextmanager
def cancel_context(event: "threading.Event | None"):
    """在 worker 线程内绑定取消事件，退出时还原（支持嵌套）。"""
    prev = getattr(_local, "cancel_event", None)
    _local.cancel_event = event
    try:
        yield
    finally:
        _local.cancel_event = prev


def is_cancelled() -> bool:
    """当前 worker 线程的任务是否已被取消。"""
    event = current_cancel_event()
    return event is not None and event.is_set()


def run_blocking_with_cancel(fn, *args, poll: float = 0.2):
    """在守护线程里跑阻塞的 `fn`，主线程（worker）轮询取消事件。

    被取消时立即抛 `CancellationError` 并丢弃仍在后台跑的守护线程；
    未取消时返回结果，`fn` 抛出的异常原样上浮。用于 LLM 调用、子进程等待、
    SQL 执行这类无法被信号直接打断的阻塞操作，让取消信号尽快生效。
    """
    holder: dict = {}
    err: dict = {}

    def target() -> None:
        try:
            holder["v"] = fn(*args)
        except BaseException as e:  # noqa: BLE001 - 原样保存，包括 CancellationError
            err["e"] = e

    t = threading.Thread(target=target, daemon=True)
    t.start()
    event = current_cancel_event()
    while t.is_alive():
        if event is not None and event.is_set():
            raise CancellationError("任务已取消")
        t.join(poll)
    if "e" in err:
        raise err["e"]
    return holder["v"]
