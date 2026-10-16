
from pydantic import BaseModel, Field


class Approval(BaseModel):
    kind: str = ""
    title: str = ""
    content: str = ""
    language: str = "python"  


class TaskView(BaseModel):
    

    task_id: str
    thread_id: str
    status: str = "running"  
    stage: str = ""  
    tool: str = ""
    plan: dict = Field(default_factory=dict)
    approval: Approval | None = None
    artifact_kind: str = ""
    artifact_code: str = ""
    rows: list[dict] = Field(default_factory=list)
    chart_spec: dict = Field(default_factory=dict)
    insights: list[str] = Field(default_factory=list)
    report: str = ""
    trace: list[dict] = Field(default_factory=list)
    logs: list[str] = Field(default_factory=list)
    memory: dict = Field(default_factory=dict)
    error: str = ""


class CreateTaskRequest(BaseModel):
    file_id: str
    question: str
    followup: bool = False
    memory: dict | None = None


class ResumeRequest(BaseModel):
    approved: bool
    modified_content: str | None = None  
