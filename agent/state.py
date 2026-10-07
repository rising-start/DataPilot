from typing import Annotated, Any, Dict, List, Literal, TypedDict


def merge_group(old: Dict[str, Any] | None, new: Dict[str, Any] | None) -> Dict[str, Any]:
    """普通分组：浅合并，节点未返回的字段保留。"""
    return {**(old or {}), **(new or {})}


def merge_run(old: Dict[str, Any] | None, new: Dict[str, Any] | None) -> Dict[str, Any]:
    """RunState：浅合并，且 error 只要本次未显式设置就归零。

    注意：LangGraph 只在节点返回了该分组时才调用 reducer，
    因此每个节点都必须至少返回 run 分组（例如写 run_logs）。
    """
    merged = {**(old or {}), **(new or {})}
    merged["error"] = (new or {}).get("error", "")
    return merged


ToolName = Literal["pandas", "sql", "dask", "none"]
ArtifactKind = Literal["sql", "pandas", "dask"]
ChartType = Literal["line", "bar", "pie", "hist", "none"]


class AnalysisPlan(TypedDict, total=False):
    goal: str
    metrics: List[str]
    dimensions: List[str]
    filters: Dict[str, Any]
    time_range: str
    tool: str
    needs_chart: bool
    chart_type: ChartType
    reason: str


class InputState(TypedDict, total=False):
    thread_id: str
    user_question: str
    followup_mode: bool
    file_path: str
    data_source_type: str


class DatasetState(TypedDict, total=False):
    dataset_profile: Dict[str, Any]
    schema_info: Dict[str, Any]
    sample_rows: List[Dict[str, Any]]


class PlanState(TypedDict, total=False):
    analysis_plan: AnalysisPlan
    selected_tool: ToolName
    needs_chart: bool


class ArtifactState(TypedDict, total=False):
    kind: ArtifactKind
    code: str
    approval_required: bool
    approved: bool
    approval_payload: Dict[str, Any]


class ExecutionState(TypedDict, total=False):
    rows: List[Dict[str, Any]]
    summary: Dict[str, Any]
    retry_count: int
    max_retries: int


class OutputState(TypedDict, total=False):
    chart_spec: Dict[str, Any]
    chart_ready: bool
    insights: List[str]
    report: str


class RunState(TypedDict, total=False):
    run_logs: List[str]
    trace: List[Dict[str, Any]]
    memory: Dict[str, Any]
    prior_questions: List[str]
    error: str
    last_error_stage: str
    terminal: bool


class AgentState(TypedDict, total=False):
    input: Annotated[InputState, merge_group]
    dataset: Annotated[DatasetState, merge_group]
    plan: Annotated[PlanState, merge_group]
    artifact: Annotated[ArtifactState, merge_group]
    execution: Annotated[ExecutionState, merge_group]
    output: Annotated[OutputState, merge_group]
    run: Annotated[RunState, merge_run]
