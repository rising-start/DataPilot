"""对外门面：UI 与评估脚本只依赖本模块，不直接读写 AgentState。"""

import uuid
from dataclasses import dataclass, field
from typing import Any

from langgraph.types import Command

import executors
from agent.graph import build_graph
from core.config import DEFAULT_MAX_RETRIES


@dataclass
class PendingApproval:
    kind: str
    title: str
    content: str
    language: str


@dataclass
class RunResult:
    thread_id: str
    status: str  # completed | awaiting_approval | failed
    tool: str = ""
    plan: dict[str, Any] = field(default_factory=dict)
    pending: PendingApproval | None = None
    artifact_kind: str = ""
    artifact_code: str = ""
    rows: list[dict[str, Any]] = field(default_factory=list)
    chart_spec: dict[str, Any] = field(default_factory=dict)
    chart_ready: bool = False
    insights: list[str] = field(default_factory=list)
    report: str = ""
    trace: list[dict[str, Any]] = field(default_factory=list)
    logs: list[str] = field(default_factory=list)
    memory: dict[str, Any] = field(default_factory=dict)
    error: str = ""


def _empty_groups() -> dict[str, Any]:
    return {
        "artifact": {
            "kind": "",
            "code": "",
            "approval_required": False,
            "approved": False,
            "approval_payload": {},
        },
        "execution": {
            "rows": [],
            "summary": {},
            "retry_count": 0,
            "max_retries": DEFAULT_MAX_RETRIES,
        },
        "output": {"chart_spec": {}, "chart_ready": False, "insights": [], "report": ""},
        "run": {"error": "", "terminal": False, "last_error_stage": ""},
    }


def _to_result(thread_id: str, raw: dict[str, Any]) -> RunResult:
    plan = raw.get("plan", {}) or {}
    artifact = raw.get("artifact", {}) or {}
    execution = raw.get("execution", {}) or {}
    output = raw.get("output", {}) or {}
    run = raw.get("run", {}) or {}

    pending = None
    status = "completed"
    interrupt_payload = raw.get("__interrupt__")
    if interrupt_payload:
        payload = interrupt_payload[0].value
        kind = payload.get("kind", "")
        pending = PendingApproval(
            kind=kind,
            title=payload.get("title", "执行审批"),
            content=payload.get("sql") or payload.get("content") or "",
            language="sql" if kind == "sql" else "python",
        )
        status = "awaiting_approval"
    elif run.get("error"):
        status = "failed"

    return RunResult(
        thread_id=thread_id,
        status=status,
        tool=plan.get("selected_tool", ""),
        plan=plan.get("analysis_plan", {}),
        pending=pending,
        artifact_kind=artifact.get("kind", ""),
        artifact_code=artifact.get("code", ""),
        rows=execution.get("rows", []),
        chart_spec=output.get("chart_spec", {}),
        chart_ready=bool(output.get("chart_ready", False)),
        insights=output.get("insights", []),
        report=output.get("report", ""),
        trace=run.get("trace", []),
        logs=run.get("run_logs", []),
        memory=run.get("memory", {}),
        error=run.get("error", ""),
    )


class AnalysisService:
    def __init__(self, graph=None):
        if graph is None:
            executors.init_executors()
            graph = build_graph()
        self._graph = graph

    @staticmethod
    def _config(thread_id: str) -> dict:
        return {"configurable": {"thread_id": thread_id}}

    def start_analysis(
        self,
        file_path: str,
        source_type: str,
        question: str,
        followup: bool = False,
        memory: dict | None = None,
        task_id: str | None = None,
    ) -> RunResult:
        # 新一轮分析使用新 thread，避免复用上一轮 checkpoint 的状态
        thread_id = str(uuid.uuid4())
        state: dict[str, Any] = {
            "input": {
                "thread_id": thread_id,
                "user_question": question,
                "followup_mode": followup,
                "file_path": file_path,
                "data_source_type": source_type,
            },
            **_empty_groups(),
        }
        if followup and memory:
            state["run"]["memory"] = memory
        # task_id 写入状态（可序列化），节点据此从进度注册表取回调上报阶段
        if task_id is not None:
            state["run"]["task_id"] = task_id

        raw = self._graph.invoke(state, config=self._config(thread_id))
        return _to_result(thread_id, raw)

    def resume(
        self,
        thread_id: str,
        approved: bool,
        task_id: str | None = None,
    ) -> RunResult:
        cmd = Command(resume=approved)
        if task_id is not None:
            # task_id 重新注入（首次分析时已存入 checkpoint，这里兜底覆盖）
            cmd = Command(resume=approved, update={"run": {"task_id": task_id}})
        raw = self._graph.invoke(cmd, config=self._config(thread_id))
        return _to_result(thread_id, raw)
