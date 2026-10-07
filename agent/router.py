from typing import Any, Dict

from core.config import DASK_ROW_THRESHOLD
from executors.registry import get_executor


def _executor_supports(tool: str, state: Dict[str, Any]) -> bool:
    try:
        return get_executor(tool).supports(state)
    except Exception:
        return False


def choose_tool(data_source_type: str, analysis_plan: Dict[str, Any], state: Dict[str, Any]) -> str:
    """
    统一工具选择逻辑：
    1. 先看数据源硬约束
    2. 再看数据规模强规则
    3. 最后再参考 planner 建议
    4. 最后兜底
    """
    planned_tool = analysis_plan.get("tool")
    row_count = (state.get("dataset", {}) or {}).get("schema_info", {}).get("row_count", 0)

    # 1. SQLite 强制走 SQL
    if data_source_type == "sqlite":
        return "sql"

    # 2. CSV / Excel 才可能走 pandas / dask
    if data_source_type in {"csv", "excel"}:
        # 大表优先 Dask
        if isinstance(row_count, int) and row_count >= DASK_ROW_THRESHOLD:
            if _executor_supports("dask", state):
                return "dask"

        # 小表再参考 planner
        if planned_tool in {"pandas", "dask", "duckdb"}:
            if _executor_supports(planned_tool, state):
                return planned_tool

        # 默认兜底 pandas
        return "pandas"

    return "none"
