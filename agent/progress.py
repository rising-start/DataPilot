"""执行阶段上报：把图节点的进入事件暴露给外部进度通道（SSE）。

节点本身保持纯函数，不直连 SSE。进度通过「task_id（写入可序列化的图状态）
+ 进程内回调注册表」传递：service 把 task_id 注入图状态，各节点进入时
调用 `report_progress(state, stage)`，再由本模块凭 task_id 从注册表取出
回调并调用。回调（函数）不进入 checkpoint，避免 LangGraph 序列化失败。
"""
from collections.abc import Callable


_REGISTRY: dict[str, Callable[[str], None]] = {}


def register_progress(task_id: str, cb: Callable[[str], None]) -> None:
    _REGISTRY[task_id] = cb


def unregister_progress(task_id: str) -> None:
    _REGISTRY.pop(task_id, None)


def report_progress(state: dict, stage: str) -> None:
    
    run = state.get("run") if isinstance(state, dict) else None
    if not isinstance(run, dict):
        return
    task_id = run.get("task_id")
    if not task_id:
        return
    cb = _REGISTRY.get(task_id)
    if callable(cb):
        cb(stage)
