from typing import Any

from agent.state import AgentState
from agent.support.tracing import run_update
from core.sanitize import make_json_safe
from executors.registry import get_executor


def _artifact_result(state: AgentState, executor, result: dict, stage: str) -> dict[str, Any]:
    """把 executor 返回的产物字段包进 artifact 分组，并补充审批信息。"""
    artifact = dict(state.get("artifact", {}))
    artifact.update({k: v for k, v in result.items() if k in {"code", "kind"}})

    merged_state = {**state, "artifact": artifact}
    need_approval = executor.needs_approval(merged_state)
    artifact["approval_required"] = need_approval
    artifact["approval_payload"] = executor.get_approval_payload(merged_state) if need_approval else {}

    update: dict[str, Any] = {"artifact": artifact}

    # retry_count 必须落在 execution 分组：路由在 after_execute_artifact 里读它，
    # 放进 run 分组会导致计数永远不递增，修复循环无法终止
    if "retry_count" in result:
        update["execution"] = {"retry_count": result["retry_count"]}

    return {
        **update,
        **run_update(
            state,
            f"{stage} by executor={executor.name}.",
            stage,
            "ok",
            {"executor": executor.name},
        ),
    }


def generate_artifact_node(state: AgentState) -> AgentState:
    try:
        executor = get_executor(state["plan"]["selected_tool"])
        result = executor.generate(state)

        if result.get("error"):
            return make_json_safe(run_update(
                state,
                f"Generate artifact failed by executor={executor.name}.",
                "generate_artifact",
                "error",
                {"executor": executor.name, "reason": result.get("error", "")},
                error=result["error"],
                terminal=bool(result.get("terminal", False)),
                last_error_stage="generate_artifact",
            ))

        return make_json_safe(_artifact_result(state, executor, result, "generate_artifact"))

    except Exception as e:
        return make_json_safe(run_update(
            state, f"Generate artifact failed: {e}", "generate_artifact", "error", {"reason": str(e)},
            error=f"Generate artifact failed: {e}", last_error_stage="generate_artifact",
        ))


def repair_artifact_node(state: AgentState) -> AgentState:
    try:
        executor = get_executor(state["plan"]["selected_tool"])
        result = executor.repair(state)

        if result.get("error"):
            return make_json_safe(run_update(
                state,
                f"Repair artifact failed by executor={executor.name}.",
                "repair_artifact",
                "error",
                {"executor": executor.name, "reason": result.get("error", "")},
                error=result["error"],
                terminal=bool(result.get("terminal", False)),
                last_error_stage="repair_artifact",
            ))

        return make_json_safe(_artifact_result(state, executor, result, "repair_artifact"))

    except Exception as e:
        return make_json_safe(run_update(
            state, f"Repair artifact failed: {e}", "repair_artifact", "error", {"reason": str(e)},
            error=f"Repair artifact failed: {e}", last_error_stage="repair_artifact",
        ))


def execute_artifact_node(state: AgentState) -> AgentState:
    try:
        executor = get_executor(state["plan"]["selected_tool"])
        result = executor.execute(state)

        if result.get("error"):
            return make_json_safe(run_update(
                state,
                f"Execute artifact failed by executor={executor.name}.",
                "execute_artifact",
                "error",
                {"executor": executor.name, "reason": result.get("error", "")},
                error=result["error"],
                terminal=bool(result.get("terminal", False)),
                last_error_stage="execute_artifact",
            ))

        return make_json_safe({
            "execution": {
                "rows": result.get("rows", []),
                "summary": result.get("summary", {}),
            },
            **run_update(
                state,
                f"Executed artifact by executor={executor.name}.",
                "execute_artifact",
                "ok",
                {"executor": executor.name, "rows": len(result.get("rows", []))},
            ),
        })

    except Exception as e:
        return make_json_safe(run_update(
            state, f"Execute artifact failed: {e}", "execute_artifact", "error", {"reason": str(e)},
            error=f"Execute artifact failed: {e}", terminal=False, last_error_stage="execute_artifact",
        ))
