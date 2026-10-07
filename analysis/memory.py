from typing import Any

import pandas as pd

from core.columns import (
    is_stable_focus_dimension,
    pick_dimension_column,
    pick_metric_column,
)
from core.sanitize import make_json_safe


def extract_memory_from_result(
    user_question: str,
    analysis_plan: dict[str, Any],
    result_df: pd.DataFrame,
) -> dict[str, Any]:
    if result_df is None or len(result_df) == 0:
        return {
            "focus_entities": {},
            "last_result": {
                "question": user_question,
                "dimension": None,
                "metric": None,
                "top_value": None,
                "top_k": [],
            },
            "result_preview": [],
        }

    dim_col = pick_dimension_column(result_df, analysis_plan)
    metric_col = pick_metric_column(result_df, analysis_plan)
    filters = analysis_plan.get("filters", {}) or {}

    top_value = None
    top_k = []

    if dim_col and metric_col and metric_col in result_df.columns and dim_col in result_df.columns:
        try:
            sorted_df = result_df.sort_values(metric_col, ascending=False).reset_index(drop=True)
            top_value = sorted_df.iloc[0][dim_col]
            top_k = make_json_safe(sorted_df[dim_col].head(3).tolist())
        except Exception:
            top_value = None
            top_k = []

    memory: dict[str, Any] = {
        "focus_entities": {},
        "last_result": {
            "question": user_question,
            "dimension": dim_col,
            "metric": metric_col,
            "top_value": top_value,
            "top_k": top_k,
        },
        "result_preview": make_json_safe(result_df.head(5).to_dict(orient="records")),
    }

    # 1. filters 里明确写出的稳定实体，优先进入 focus
    for k, v in filters.items():
        if (
            isinstance(v, (str, int, float))
            and str(v).strip()
            and is_stable_focus_dimension(k)
        ):
            memory["focus_entities"][str(k)] = v

    # 2. 如果没有明确 filters，但当前主维度本身是稳定维度，
    #    且 top_value 存在，则强制把 top_value 写进 focus
    if (
        dim_col
        and is_stable_focus_dimension(dim_col)
        and top_value is not None
        and str(dim_col) not in memory["focus_entities"]
    ):
        memory["focus_entities"][str(dim_col)] = top_value

    return make_json_safe(memory)
