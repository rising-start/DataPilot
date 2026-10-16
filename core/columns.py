"""维度列 / 指标列的统一选择逻辑（图表与报告共用）。"""

from __future__ import annotations

from typing import Any

import pandas as pd

PREFERRED_METRIC_ORDER = [
    "refund_rate",
    "growth_rate",
    "gross_margin",
    "gross_margin_rate",
    "sales_amount",
    "total_sales",
    "sales",
    "profit",
    "avg_sales",
    "avg_order_value",
    "refund_amount",
    "refund_orders",
    "order_count",
    "total_orders",
]


WEAK_METRIC_COLUMNS = {"order_id", "customer_id", "refund_flag"}


TRANSIENT_DIMENSION_KEYWORDS = (
    "channel",
    "month",
    "date",
    "time",
    "order_date",
    "dt",
    "week",
    "day",
)


def pick_dimension_column(result_df: pd.DataFrame, analysis_plan: dict[str, Any]) -> str | None:
    
    for dim in analysis_plan.get("dimensions", []) or []:
        if dim in result_df.columns:
            return dim

    non_numeric_cols = result_df.select_dtypes(exclude="number").columns.tolist()
    if non_numeric_cols:
        return non_numeric_cols[0]

    if len(result_df.columns) > 0:
        return result_df.columns[0]

    return None


def pick_metric_column(result_df: pd.DataFrame, analysis_plan: dict[str, Any]) -> str | None:
    
    numeric_cols = result_df.select_dtypes(include="number").columns.tolist()
    if not numeric_cols:
        return None

    for col in PREFERRED_METRIC_ORDER:
        if col in numeric_cols:
            return col

    for metric in analysis_plan.get("metrics", []) or []:
        if metric in numeric_cols:
            return metric

    strong_numeric = [c for c in numeric_cols if c not in WEAK_METRIC_COLUMNS]
    if strong_numeric:
        return strong_numeric[0]

    return numeric_cols[0]


def is_stable_focus_dimension(dim_col: str | None) -> bool:
    
    if not dim_col:
        return False

    lowered = str(dim_col).lower()
    return not any(keyword in lowered for keyword in TRANSIENT_DIMENSION_KEYWORDS)
