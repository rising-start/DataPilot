import json

from agent.prompts import PLANNER_SYSTEM_PROMPT
from agent.router import choose_tool
from agent.state import AgentState
from agent.support.plan_schema import coerce_plan
from agent.support.tracing import run_update
from core.sanitize import make_json_safe
from core.schema import build_schema_summary_for_llm
from llm.client import invoke_json


def plan_analysis_node(state: AgentState) -> AgentState:
    try:
        data_input = state.get("input", {})
        run = state.get("run", {}) or {}
        user_question = data_input.get("user_question")
        data_source_type = data_input.get("data_source_type")

        if not user_question:
            return make_json_safe(run_update(
                state, "Plan analysis failed: missing user_question.", "plan_analysis", "error",
                {"reason": "missing user_question"},
                error="Missing user_question in state.", last_error_stage="plan_analysis",
            ))

        if not data_source_type:
            return make_json_safe(run_update(
                state, "Plan analysis failed: missing data_source_type.", "plan_analysis", "error",
                {"reason": "missing data_source_type"},
                error="Missing data_source_type in state.", last_error_stage="plan_analysis",
            ))

        payload = {
            "user_question": user_question,
            "data_source_type": data_source_type,
            "schema_info": build_schema_summary_for_llm(state),
            "previous_questions": run.get("prior_questions", []),
            "followup_mode": data_input.get("followup_mode", False),
            "memory_context": run.get("memory", {}),
        }

        plan = coerce_plan(invoke_json(PLANNER_SYSTEM_PROMPT, json.dumps(payload, ensure_ascii=False)))
        selected_tool = choose_tool(data_source_type, plan, state)

        if selected_tool == "none":
            # 必须显式写 error，否则 error 节点拿到空 error，最终状态会被误判为成功
            return make_json_safe(run_update(
                state,
                f"No executor available for data source: {data_source_type}.",
                "plan_analysis",
                "error",
                {"reason": "no executor"},
                error=f"Unsupported data source type: {data_source_type}",
                last_error_stage="plan_analysis",
            ))

        return make_json_safe({
            "plan": {
                "analysis_plan": plan,
                "selected_tool": selected_tool,
                "needs_chart": bool(plan.get("needs_chart", False)),
            },
            **run_update(
                state, f"Built analysis plan with tool={selected_tool}.", "plan_analysis", "ok",
                {
                    "tool": selected_tool,
                    "goal": plan.get("goal"),
                    "dimensions": plan.get("dimensions", []),
                    "metrics": plan.get("metrics", []),
                    "memory_keys": list((run.get("memory", {}) or {}).keys()),
                },
            ),
        })

    except Exception as e:
        return make_json_safe(run_update(
            state, f"Plan analysis failed: {e}", "plan_analysis", "error", {"reason": str(e)},
            error=f"Plan analysis failed: {e}", last_error_stage="plan_analysis",
        ))
