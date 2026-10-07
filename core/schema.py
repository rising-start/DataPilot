from __future__ import annotations

from typing import Any

from core.sanitize import make_json_safe


def build_schema_summary_for_llm(state: dict[str, Any]) -> dict[str, Any]:
    """给 LLM 使用的 schema 摘要（agent 与 executor 共用）。"""
    data_input = state.get("input", {}) or {}
    dataset = state.get("dataset", {}) or {}

    if data_input.get("data_source_type") == "sqlite":
        return make_json_safe(dataset.get("schema_info", {}))

    schema_info = dataset.get("schema_info", {}) or {}
    return make_json_safe(
        {
            "columns": schema_info.get("columns", []),
            "row_count": schema_info.get("row_count", 0),
            "sample_rows": (dataset.get("sample_rows", []) or [])[:3],
        }
    )
