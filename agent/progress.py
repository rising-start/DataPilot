"""执行阶段上报：把图节点的进入事件暴露给外部进度通道（SSE）。

节点本身保持纯函数，不直连 SSE。进度通过「task_id（写入可序列化的图状态）
+ 进程内回调注册表」传递：service 把 task_id 注入图状态，各节点进入时
调用 `report_progress(state, stage)`，再由本模块凭 task_id 从注册表取出
回调并调用。回调（函数）不进入 checkpoint，避免 LangGraph 序列化失败。
"""
from collections.abc import Callable

# task_id -> 进度回调（运行时注册，进程内有效；任务终态后清理）
_REGISTRY: dict[str, Callable[[str], None]] = {}


def register_progress(task_id: str, cb: Callable[[str], None]) -> None:
    _REGISTRY[task_id] = cb


def unregister_progress(task_id: str) -> None:
    _REGISTRY.pop(task_id, None)


def report_progress(state: dict, stage: str) -> None:
    """节点进入时调用，凭 task_id 从注册表取出回调并上报当前阶段。

    `state` 是 LangGraph 传给节点的状态字典；`task_id` 由 service 在发起
    分析时写入 `run["task_id"]`（可序列化字符串）。
    """
    run = state.get("run") if isinstance(state, dict) else None
    if not isinstance(run, dict):
        return
    task_id = run.get("task_id")
    if not task_id:
        return
    cb = _REGISTRY.get(task_id)
    if callable(cb):
        cb(stage)
