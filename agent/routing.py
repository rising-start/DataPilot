from agent.state import AgentState


def _run(state: AgentState) -> dict:
    return state.get("run", {}) or {}


def _artifact(state: AgentState) -> dict:
    return state.get("artifact", {}) or {}


def _plan(state: AgentState) -> dict:
    return state.get("plan", {}) or {}


def _execution(state: AgentState) -> dict:
    return state.get("execution", {}) or {}


def after_load_data(state: AgentState) -> str:
    """load_data → plan_analysis 之间必须有条件边，否则加载失败会被后续节点清零。"""
    if _run(state).get("error"):
        return "error"
    return "plan_analysis"


def after_plan(state: AgentState) -> str:
    if _run(state).get("error"):
        return "error"
    if _plan(state).get("selected_tool") == "none":
        return "error"
    return "generate_artifact"


def after_generate_artifact(state: AgentState) -> str:
    if _run(state).get("error"):
        return "error"
    if _artifact(state).get("approval_required", False):
        return "approval"
    return "execute_artifact"


def after_approval(state: AgentState) -> str:
    if _run(state).get("error"):
        return "error"
    return "execute_artifact"


def after_execute_artifact(state: AgentState) -> str:
    run = _run(state)
    if run.get("error"):
        # 用户拒绝执行等终止性错误不再重试，否则会再次生成并重新请求审批
        if run.get("terminal", False):
            return "error"
        if _execution(state).get("retry_count", 0) < _execution(state).get("max_retries", 1):
            return "repair_artifact"
        return "error"

    if _plan(state).get("needs_chart", False):
        return "build_chart"

    return "report"


def after_repair_artifact(state: AgentState) -> str:
    if _run(state).get("error"):
        return "error"

    if _artifact(state).get("approval_required", False):
        return "approval"
    return "execute_artifact"


def after_build_chart(state: AgentState) -> str:
    if _run(state).get("error"):
        return "error"
    return "report"
