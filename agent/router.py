from typing import Any

from core.config import DASK_ROW_THRESHOLD
from executors.registry import get_executor


def _executor_supports(tool: str, state: dict[str, Any]) -> bool:
    try:
        return get_executor(tool).supports(state)
    except Exception:
        return False


def choose_tool(data_source_type: str, analysis_plan: dict[str, Any], state: dict[str, Any]) -> str:
    
    planned_tool = analysis_plan.get("tool")
    row_count = (state.get("dataset", {}) or {}).get("schema_info", {}).get("row_count", 0)

    
    if data_source_type == "sqlite":
        return "sql"

    
    if data_source_type in {"csv", "excel"}:
        
        if isinstance(row_count, int) and row_count >= DASK_ROW_THRESHOLD:
            if _executor_supports("dask", state):
                return "dask"

        
        if planned_tool in {"pandas", "dask", "duckdb"}:
            if _executor_supports(planned_tool, state):
                return planned_tool

        
        return "pandas"

    return "none"
