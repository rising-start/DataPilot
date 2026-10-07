from typing import Any

from agent.state import AnalysisPlan

ALLOWED_CHART_TYPES = {"line", "bar", "pie", "hist", "none"}
ALLOWED_TOOLS = {"pandas", "sql", "dask"}


def _as_str(value: Any) -> str:
    return value if isinstance(value, str) else ""


def _as_str_list(value: Any) -> list[str]:
    # 只接受列表类输入；非列表（含裸字符串）直接视为空，避免把脏数据当维度/指标
    if not isinstance(value, (list, tuple)):
        return []
    return [v for v in value if isinstance(v, str) and v.strip()]


def coerce_plan(raw: Any) -> AnalysisPlan:
    """把 LLM 返回的裸 dict 收敛成受校验的 AnalysisPlan。"""
    if not isinstance(raw, dict):
        raw = {}

    tool = raw.get("tool")
    chart_type = raw.get("chart_type")

    return AnalysisPlan(
        goal=_as_str(raw.get("goal")),
        metrics=_as_str_list(raw.get("metrics")),
        dimensions=_as_str_list(raw.get("dimensions")),
        filters=raw.get("filters") if isinstance(raw.get("filters"), dict) else {},
        time_range=_as_str(raw.get("time_range")),
        tool=tool if tool in ALLOWED_TOOLS else None,
        needs_chart=bool(raw.get("needs_chart", False)),
        chart_type=chart_type if chart_type in ALLOWED_CHART_TYPES else "none",
        reason=_as_str(raw.get("reason")),
    )
