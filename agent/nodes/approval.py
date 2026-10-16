from langgraph.types import interrupt

from agent.state import AgentState
from agent.support.tracing import run_update
from core.sanitize import make_json_safe
from safety.sql_guard import is_safe_sql


def approval_node(state: AgentState) -> AgentState:
    payload = state.get("artifact", {}).get("approval_payload", {})
    decision = interrupt(payload)

    
    if isinstance(decision, dict):
        approved = bool(decision.get("approved"))
        code = decision.get("code")
    else:
        approved = bool(decision)
        code = None

    artifact = dict(state.get("artifact", {}) or {})
    artifact["approved"] = approved

    
    
    if code is not None and code != artifact.get("code", ""):
        if payload.get("kind") == "sql":
            ok, reason = is_safe_sql(code)
            if not ok:
                return make_json_safe(run_update(
                    state,
                    f"Modified SQL rejected by guard: {reason}",
                    "approval",
                    "error",
                    {"reason": reason},
                    error=f"修改后的 SQL 未通过安全检查：{reason}",
                    terminal=True,
                    last_error_stage="approval",
                ))
        artifact["code"] = code

    return make_json_safe({
        "artifact": artifact,
        **run_update(
            state,
            f"Approval result: approved={approved}, modified={'yes' if code else 'no'}",
            "approval",
            "ok",
            {"approved": approved, "modified": code is not None},
        ),
    })
