from typing import Any, Dict

import pandas as pd

from core.columns import pick_dimension_column, pick_metric_column


def build_chart_spec(result_df: pd.DataFrame, analysis_plan: Dict[str, Any]) -> Dict[str, Any]:
    """生成图表规格（v1）。

    返回结构：
      chart_type: bar | line | pie | hist | none
      x:          维度列
      y:          主指标列
      series:     数值列（多指标时多个），前端 ECharts 据此渲染
      title:      标题
    """
    chart_type = analysis_plan.get("chart_type", "none")
    title = analysis_plan.get("goal", "Analysis Chart")

    x = pick_dimension_column(result_df, analysis_plan)
    y = pick_metric_column(result_df, analysis_plan)

    numeric_cols = result_df.select_dtypes(include="number").columns.tolist()
    metrics = [m for m in (analysis_plan.get("metrics") or []) if m in numeric_cols]
    series = metrics or ([y] if y else [])

    # 需要数值列却没有可用数值列时，不渲染图表
    if chart_type in {"line", "bar", "pie", "hist"} and not series:
        chart_type = "none"
        series = []

    return {
        "chart_type": chart_type,
        "x": x,
        "y": y,
        "series": series,
        "title": title,
    }
