from typing import Any

from agent.state import AgentState
from core.sanitize import make_json_safe


def append_log(state: AgentState, message: str) -> list[str]:
    logs = list(state.get("run", {}).get("run_logs", []))
    logs.append(message)
    return logs


def append_trace(
    state: AgentState,
    stage: str,
    status: str,
    detail: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    trace = list(state.get("run", {}).get("trace", []))
    trace.append(
        {
            "stage": str(stage),
            "status": str(status),
            "detail": make_json_safe(detail or {}),
        }
    )
    return trace


def run_update(
    state: AgentState,
    message: str,
    stage: str,
    status: str,
    detail: dict[str, Any] | None = None,
    **extra: Any,
) -> dict[str, Any]:
    """统一构造 run 分组更新。

    每个节点都必须返回 run 分组，否则 merge_run 不会触发，error 也就不会归零。
    """
    payload: dict[str, Any] = {
        "run_logs": append_log(state, message),
        "trace": append_trace(state, stage, status, detail),
    }
    payload.update(extra)
    return {"run": payload}
