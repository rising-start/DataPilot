import pandas as pd

from agent.state import AgentState
from agent.support.tracing import run_update
from analysis.memory import extract_memory_from_result
from analysis.report import build_report
from core.columns import is_stable_focus_dimension
from core.config import MAX_FOCUS_ENTITIES
from core.sanitize import make_json_safe


def report_node(state: AgentState) -> AgentState:
    try:
        data_input = state.get("input", {})
        analysis_plan = state.get("plan", {}).get("analysis_plan", {})
        rows = state.get("execution", {}).get("rows", [])
        result_df = pd.DataFrame(rows)
        user_question = data_input.get("user_question", "")

        insights, report = build_report(
            user_question=user_question,
            analysis_plan=analysis_plan,
            result_df=result_df,
        )

        new_memory = extract_memory_from_result(
            user_question=user_question,
            analysis_plan=analysis_plan,
            result_df=result_df,
        )

        run_state = state.get("run", {})
        previous = list(run_state.get("prior_questions", []))
        previous.append(user_question)

        old_memory = dict(run_state.get("memory", {}))
        merged_memory = dict(old_memory)

        # 空结果会产出一个全 None 的 last_result，此时保留上一轮结果，
        # 否则“刚才那个地区”这类指代会失去依据
        if result_df.empty and old_memory.get("last_result"):
            merged_memory["last_result"] = old_memory["last_result"]
        else:
            merged_memory["last_result"] = new_memory.get("last_result") or {}

        merged_memory["result_preview"] = new_memory.get("result_preview", [])

        old_focus = dict(old_memory.get("focus_entities", {}))
        new_focus = dict(new_memory.get("focus_entities", {}))

        cleaned_new_focus = {}
        for k, v in new_focus.items():
            if isinstance(k, str) and k.strip() and is_stable_focus_dimension(k):
                cleaned_new_focus[k.strip()] = v

        old_focus.update(cleaned_new_focus)
        if len(old_focus) > MAX_FOCUS_ENTITIES:
            old_focus = dict(list(old_focus.items())[-MAX_FOCUS_ENTITIES:])

        merged_memory["focus_entities"] = old_focus

        return make_json_safe({
            "output": {"insights": insights, "report": report},
            **run_update(
                state,
                "Built final report.",
                "report",
                "ok",
                {
                    "insights_count": len(insights),
                    "memory_keys": list(merged_memory.keys()),
                    "focus_entities": merged_memory.get("focus_entities", {}),
                },
                memory=merged_memory,
                prior_questions=previous,
            ),
        })

    except Exception as e:
        return make_json_safe(run_update(
            state, f"Report generation failed: {e}", "report", "error", {"reason": str(e)},
            error=f"Report generation failed: {e}", last_error_stage="report",
        ))
