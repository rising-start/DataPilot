from agent.state import AgentState
from agent.support.tracing import run_update
from core.sanitize import make_json_safe


def error_node(state: AgentState) -> AgentState:
    error = state.get("run", {}).get("error", "unknown error")
    return make_json_safe({
        "output": {"report": f"执行失败：{error}"},
        
        
        **run_update(state, "Entered error node.", "error", "ok", {"error": error}, error=error),
    })
