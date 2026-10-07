import pandas as pd

from agent.state import AgentState
from agent.support.tracing import run_update
from core.sanitize import make_json_safe
from viz.chart import build_chart_spec


def build_chart_node(state: AgentState) -> AgentState:
    try:
        rows = state.get("execution", {}).get("rows", [])
        result_df = pd.DataFrame(rows)

        if result_df.empty:
            return make_json_safe({
                "output": {"chart_spec": {}, "chart_ready": False},
                **run_update(
                    state, "Skipped chart building because result is empty.", "build_chart", "ok",
                    {"skipped": True, "reason": "empty result"},
                ),
            })

        chart_spec = build_chart_spec(result_df, state.get("plan", {}).get("analysis_plan", {}))

        if chart_spec.get("chart_type") == "none":
            return make_json_safe({
                "output": {"chart_spec": chart_spec, "chart_ready": False},
                **run_update(
                    state, "Skipped chart building because chart_type is none.", "build_chart", "ok",
                    {"skipped": True, "reason": "chart_type=none"},
                ),
            })

        return make_json_safe({
            "output": {"chart_spec": chart_spec, "chart_ready": True},
            **run_update(state, "Built chart spec.", "build_chart", "ok", {"chart_spec": chart_spec}),
        })

    except Exception as e:
        return make_json_safe(run_update(
            state, f"Build chart failed: {e}", "build_chart", "error", {"reason": str(e)},
            error=f"Build chart failed: {e}", last_error_stage="build_chart",
        ))
