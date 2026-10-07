from typing import List, Optional

from pydantic import BaseModel, Field


class Approval(BaseModel):
    kind: str = ""
    title: str = ""
    content: str = ""
    language: str = "python"  # sql | python


class TaskView(BaseModel):
    """与 service.RunResult 字段一一对应，供前端消费。"""

    task_id: str
    thread_id: str
    status: str = "running"  # running | awaiting_approval | completed | failed
    tool: str = ""
    plan: dict = Field(default_factory=dict)
    approval: Optional[Approval] = None
    artifact_kind: str = ""
    artifact_code: str = ""
    rows: List[dict] = Field(default_factory=list)
    chart_spec: dict = Field(default_factory=dict)
    insights: List[str] = Field(default_factory=list)
    report: str = ""
    trace: List[dict] = Field(default_factory=list)
    logs: List[str] = Field(default_factory=list)
    memory: dict = Field(default_factory=dict)
    error: str = ""


class CreateTaskRequest(BaseModel):
    file_id: str
    question: str
    followup: bool = False
    memory: Optional[dict] = None


class ResumeRequest(BaseModel):
    approved: bool
