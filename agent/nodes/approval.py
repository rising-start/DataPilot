from langgraph.types import interrupt

from agent.state import AgentState
from agent.support.tracing import run_update
from core.sanitize import make_json_safe


def approval_node(state: AgentState) -> AgentState:
    payload = state.get("artifact", {}).get("approval_payload", {})
    approved = interrupt(payload)

    return make_json_safe({
        "artifact": {"approved": bool(approved)},
        **run_update(
            state,
            f"Approval result: {approved}",
            "approval",
            "ok",
            {"approved": bool(approved)},
        ),
    })
