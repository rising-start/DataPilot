# DataPilot Vue 前端 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 用 Vue3 SPA 替换 Streamlit 前端，后端新增 FastAPI 薄 API 层承载任务语义（含中途审批），`service.py` 及以下各层不改。

**Architecture:** `server/`（FastAPI）作为 `service.AnalysisService` 的薄封装，任务提交到线程池、状态存内存、`TaskView` 与 `RunResult` 字段一一对应；`web/`（Vue3 + TS + Vite + Element Plus + ECharts）通过 5 个 REST 接口 + 2 秒轮询消费；图表改为前端 ECharts 渲染，移除 matplotlib。

**Tech Stack:** Python 3.11+、FastAPI、uvicorn、python-multipart、pytest；Node 22、Vue 3、TypeScript、Vite、Element Plus、ECharts、Vitest。

## Global Constraints

- 环境 Windows + PowerShell；命令前缀 `cd c:/Users/86159/PycharmProjects/SQLanalysis;`。
- **本项目不使用版本控制**（用户选择）：所有任务**不执行 git 命令**，也不写 commit 步骤。
- `service.py`、`agent/`、`executors/`、`core/`、`safety/`、`llm/`、`analysis/` 的业务规则一律不改。
- 测试不得发起真实网络请求；后端测试用 FakeExecutor + monkeypatch（沿用 `tests/test_service.py` 的做法）。
- 每步完成后运行 `python -m compileall -q server service.py agent executors core safety llm analysis viz`（逐步按存在的目录调整）。
- 已有 55 条 Python 测试必须保持通过。
- 命名与字段必须与 spec 一致：`TaskView` / `Approval` / `chart_spec v1`（含 `series`）/ 状态值 `running|awaiting_approval|completed|failed`。
- 环境变量：`QIANFAN_API_KEY` 必需，`QIANFAN_MODEL` 显式设为账号可用模型（默认 `deepseek-v3.2`）。

---

### Task 1: 后端骨架 —— 依赖与任务存储

**Files:**
- Create: `server/__init__.py`、`server/main.py`、`server/schemas.py`、`server/task_store.py`、`server/files.py`
- Modify: `requirements.txt`
- Test: `tests/test_task_store.py`

**Interfaces:**
- Consumes: `service.AnalysisService`、`service.RunResult`、`core.files.{detect_source_type,save_upload_to_temp,delete_temp_file}`
- Produces: `server.schemas.{TaskView,Approval,CreateTaskRequest,ResumeRequest}`、`server.task_store.{get,set,delete,list}`（后续路由依赖）

- [ ] **Step 1: 加依赖**

```bash
cd c:/Users/86159/PycharmProjects/SQLanalysis; pip install "fastapi" "uvicorn[standard]" python-multipart
```
`requirements.txt` 移除 `streamlit`、`matplotlib`，新增三行：`fastapi`、`uvicorn[standard]`、`python-multipart`

- [ ] **Step 2: 写失败测试**

```python
# tests/test_task_store.py
from server.schemas import TaskView
from server.task_store import InMemoryTaskStore, TaskRecord


def test_store_roundtrip():
    store = InMemoryTaskStore()
    record = TaskRecord(task_id="t1", thread_id="th1", status="running")
    store.set(record)
    assert store.get("t1").task_id == "t1"
    assert store.get("missing") is None


def test_store_delete_and_list():
    store = InMemoryTaskStore()
    store.set(TaskRecord(task_id="a", thread_id="1", status="running"))
    store.set(TaskRecord(task_id="b", thread_id="2", status="completed"))
    assert len(store.list()) == 2
    store.delete("a")
    assert store.get("a") is None
    assert [r.task_id for r in store.list()] == ["b"]


def test_task_view_defaults():
    view = TaskView(task_id="t", thread_id="th", status="running")
    assert view.rows == [] and view.insights == [] and view.approval is None
    assert view.error == ""
```

- [ ] **Step 3: 运行确认失败**

```bash
cd c:/Users/86159/PycharmProjects/SQLanalysis; python -m pytest tests/test_task_store.py -q
```
Expected: FAIL，`No module named 'server'`

- [ ] **Step 4: 实现 schemas 与 task_store**

```python
# server/schemas.py
from typing import List, Optional

from pydantic import BaseModel, Field


class Approval(BaseModel):
    kind: str = ""
    title: str = ""
    content: str = ""
    language: str = "python"   # sql | python


class TaskView(BaseModel):
    task_id: str
    thread_id: str
    status: str = "running"    # running | awaiting_approval | completed | failed
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
```

```python
# server/task_store.py
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from service import RunResult


@dataclass
class TaskRecord:
    task_id: str
    thread_id: str
    status: str = "running"
    file_path: str = ""
    result: Optional[RunResult] = None
    error: str = ""
    extra: dict = field(default_factory=dict)


class InMemoryTaskStore:
    """内存任务存储。接口按 Redis 语义设计，后续可替换实现而路由不动。"""

    def __init__(self) -> None:
        self._records: Dict[str, TaskRecord] = {}

    def get(self, task_id: str) -> Optional[TaskRecord]:
        return self._records.get(task_id)

    def set(self, record: TaskRecord) -> None:
        self._records[record.task_id] = record

    def delete(self, task_id: str) -> None:
        self._records.pop(task_id, None)

    def list(self) -> List[TaskRecord]:
        return list(self._records.values())
```

- [ ] **Step 5: 运行确认通过**

```bash
cd c:/Users/86159/PycharmProjects/SQLanalysis; python -m pytest tests/test_task_store.py -q
```
Expected: 3 passed

- [ ] **Step 6: `server/files.py`（上传落盘）**

```python
# server/files.py
from dataclasses import dataclass

from core.files import detect_source_type, delete_temp_file, save_upload_to_temp


@dataclass
class UploadedFile:
    file_id: str
    filename: str
    source_type: str
    path: str


class UploadStore:
    """上传文件登记表：file_id -> 临时路径。多轮追问会复用同一个 file_id，
    因此任务终态不得删除临时文件。"""

    def __init__(self) -> None:
        self._files: dict[str, UploadedFile] = {}

    def save(self, file_id: str, filename: str, data: bytes) -> UploadedFile:
        path = save_upload_to_temp(filename, data)
        uploaded = UploadedFile(file_id, filename, detect_source_type(filename), path)
        self._files[file_id] = uploaded
        return uploaded

    def get(self, file_id: str):
        return self._files.get(file_id)

    def delete(self, file_id: str) -> None:
        uploaded = self._files.pop(file_id, None)
        if uploaded:
            delete_temp_file(uploaded.path)


UPLOADS = UploadStore()
```

---

### Task 2: 后端路由 —— 上传、建任务、查询、审批、清理

**Files:**
- Create: `server/api/__init__.py`、`server/api/tasks.py`
- Modify: `server/main.py`
- Test: `tests/test_api_tasks.py`

**Interfaces:**
- Consumes: `server.schemas.*`、`server.task_store.InMemoryTaskStore`、`server.files.UPLOADS`、`service.AnalysisService`
- Produces: 5 个 HTTP 路由（Task 4 前端依赖这些路径与字段名）

- [ ] **Step 1: 写失败测试**

```python
# tests/test_api_tasks.py
import io
import time

import pandas as pd
import pytest
from fastapi.testclient import TestClient

import agent.nodes.plan as plan_nodes


PLAN = {
    "goal": "各渠道销售额", "metrics": ["sales_amount"], "dimensions": ["channel"],
    "filters": {}, "time_range": "", "tool": "pandas",
    "needs_chart": True, "chart_type": "bar", "reason": "",
}


class FakeExecutor:
    """最小执行器：generate 返回代码，execute 按 approved 决定成败。"""

    name = "pandas"

    def __init__(self):
        self.approved_seen = None

    def supports(self, state):
        return True

    def generate(self, state):
        return {"code": "result_df = df.head(2)", "kind": "pandas", "error": ""}

    def repair(self, state):
        return {"code": "result_df = df.head(1)", "kind": "pandas", "error": "", "retry_count": 1}

    def needs_approval(self, state):
        return True

    def get_approval_payload(self, state):
        return {
            "kind": "pandas", "title": "代码执行审批",
            "content": state.get("artifact", {}).get("code", ""), "message": "ok?",
        }

    def execute(self, state):
        artifact = state.get("artifact", {}) or {}
        self.approved_seen = artifact.get("approved", False)
        if artifact.get("approval_required", False) and not artifact.get("approved", False):
            return {"rows": [], "summary": {}, "error": "Code execution not approved.", "terminal": True}
        df = pd.DataFrame({"channel": ["线上"], "sales_amount": [1.0]})
        return {"rows": df.to_dict(orient="records"), "summary": {}, "error": "", "terminal": False}


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(plan_nodes, "invoke_json", lambda *a, **k: dict(PLAN))
    import executors
    import server.api.tasks as tasks_api
    from server.main import app

    executors.init_executors()
    fake = FakeExecutor()
    executors.register_executor(fake)
    tasks_api.set_executor_for_test(fake)

    with TestClient(app) as c:
        yield c
    executors.registry._EXECUTOR_REGISTRY.clear()


def _wait_terminal(client, task_id, timeout=20):
    for _ in range(timeout * 10):
        resp = client.get(f"/api/tasks/{task_id}")
        assert resp.status_code == 200
        view = resp.json()
        if view["status"] in ("awaiting_approval", "completed", "failed"):
            return view
        time.sleep(0.1)
    raise AssertionError("task did not reach terminal state")


def _upload(client):
    csv = b"channel,sales_amount\nA,10\nB,20\n"
    resp = client.post("/api/files", files={"file": ("demo.csv", io.BytesIO(csv), "text/csv")})
    assert resp.status_code == 200
    return resp.json()


def test_upload_returns_file_id(client):
    body = _upload(client)
    assert body["file_id"] and body["source_type"] == "csv"


def test_task_reaches_awaiting_approval(client):
    body = _upload(client)
    resp = client.post("/api/tasks", json={"file_id": body["file_id"], "question": "各渠道销售额"})
    assert resp.status_code == 200
    view = _wait_terminal(client, resp.json()["task_id"])
    assert view["status"] == "awaiting_approval"
    assert view["approval"] is not None
    assert view["approval"]["language"] == "python"


def test_approve_completes(client):
    body = _upload(client)
    task_id = client.post("/api/tasks", json={"file_id": body["file_id"], "question": "各渠道销售额"}).json()["task_id"]
    _wait_terminal(client, task_id)

    resp = client.post(f"/api/tasks/{task_id}/resume", json={"approved": True})
    assert resp.status_code == 200
    view = _wait_terminal(client, task_id)
    assert view["status"] == "completed"
    assert view["rows"] and view["report"]


def test_reject_terminates(client):
    body = _upload(client)
    task_id = client.post("/api/tasks", json={"file_id": body["file_id"], "question": "各渠道销售额"}).json()["task_id"]
    _wait_terminal(client, task_id)

    client.post(f"/api/tasks/{task_id}/resume", json={"approved": False})
    view = _wait_terminal(client, task_id)
    assert view["status"] == "failed"
    assert view["approval"] is None
    assert "not approved" in view["error"].lower()


def test_unknown_task_returns_404(client):
    assert client.get("/api/tasks/does-not-exist").status_code == 404


def test_health(client):
    assert client.get("/api/health").json() == {"status": "ok"}
```

- [ ] **Step 2: 运行确认失败**

```bash
cd c:/Users/86159/PycharmProjects/SQLanalysis; python -m pytest tests/test_api_tasks.py -q
```
Expected: FAIL，`No module named 'server.main'`

- [ ] **Step 3: 实现路由**

```python
# server/api/tasks.py
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

from fastapi import APIRouter, HTTPException, UploadFile, File

from core.files import detect_source_type
from server.files import UPLOADS
from server.schemas import (
    CreateTaskRequest,
    ResumeRequest,
    TaskView,
)
from server.task_store import InMemoryTaskStore, TaskRecord
from service import AnalysisService, RunResult

router = APIRouter(prefix="/api")
STORE = InMemoryTaskStore()
SERVICE = AnalysisService()
EXECUTOR = ThreadPoolExecutor(max_workers=4)

_TEST_EXECUTOR = None


def set_executor_for_test(executor) -> None:
    """仅测试用：替换测试期望的执行器。"""
    global _TEST_EXECUTOR
    _TEST_EXECUTOR = executor


def _to_view(record: TaskRecord) -> TaskView:
    result: Optional[RunResult] = record.result
    if result is None:
        return TaskView(
            task_id=record.task_id,
            thread_id=record.thread_id,
            status=record.status,
            error=record.error,
        )

    approval = None
    if result.pending is not None:
        approval = {
            "kind": result.pending.kind,
            "title": result.pending.title,
            "content": result.pending.content,
            "language": result.pending.language,
        }

    return TaskView(
        task_id=record.task_id,
        thread_id=result.thread_id,
        status=record.status,
        tool=result.tool,
        plan=result.plan,
        approval=approval,
        artifact_kind=result.artifact_kind,
        artifact_code=result.artifact_code,
        rows=result.rows,
        chart_spec=result.chart_spec,
        insights=result.insights,
        report=result.report,
        trace=result.trace,
        logs=result.logs,
        memory=result.memory,
        error=result.error or record.error,
    )


def _resolve_status(result: RunResult) -> str:
    return result.status


@router.get("/health")
def health():
    return {"status": "ok"}


@router.post("/files")
def upload_file(file: UploadFile = File(...)):
    file_id = str(uuid.uuid4())
    data = file.file.read()
    uploaded = UPLOADS.save(file_id, file.filename or "upload", data)
    return {"file_id": file_id, "filename": uploaded.filename, "source_type": uploaded.source_type}


@router.post("/tasks")
def create_task(payload: CreateTaskRequest):
    uploaded = UPLOADS.get(payload.file_id)
    if uploaded is None:
        raise HTTPException(status_code=404, detail="file_id not found")

    task_id = str(uuid.uuid4())
    record = TaskRecord(task_id=task_id, thread_id="", status="running", file_path=uploaded.path)
    STORE.set(record)

    def run() -> None:
        try:
            result = SERVICE.start_analysis(
                uploaded.path,
                uploaded.source_type,
                payload.question,
                followup=payload.followup,
                memory=payload.memory,
            )
            record.thread_id = result.thread_id
            record.status = _resolve_status(result)
            record.result = result
        except Exception as e:  # noqa: BLE001
            record.status = "failed"
            record.error = str(e)
        STORE.set(record)

    EXECUTOR.submit(run)
    return {"task_id": task_id, "status": "running"}


@router.get("/tasks/{task_id}")
def get_task(task_id: str):
    record = STORE.get(task_id)
    if record is None:
        raise HTTPException(status_code=404, detail="task not found")
    return _to_view(record)


@router.post("/tasks/{task_id}/resume")
def resume_task(task_id: str, payload: ResumeRequest):
    record = STORE.get(task_id)
    if record is None:
        raise HTTPException(status_code=404, detail="task not found")

    thread_id = record.thread_id or (record.result.thread_id if record.result else "")
    if not thread_id:
        raise HTTPException(status_code=409, detail="task has no thread to resume")

    record.status = "running"
    STORE.set(record)

    def run() -> None:
        try:
            result = SERVICE.resume(thread_id, payload.approved)
            record.status = _resolve_status(result)
            record.result = result
        except Exception as e:  # noqa: BLE001
            record.status = "failed"
            record.error = str(e)
        STORE.set(record)

    EXECUTOR.submit(run)
    return {"task_id": task_id, "status": "running"}


@router.delete("/tasks/{task_id}")
def delete_task(task_id: str):
    STORE.delete(task_id)
    return {"deleted": True}


@router.get("/tasks/{task_id}/events")
def task_events(task_id: str):
    raise HTTPException(status_code=501, detail="SSE not implemented in this stage")
```

- [ ] **Step 4: `server/main.py`**

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from server.api.tasks import router

app = FastAPI(title="DataPilot API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)

# 前端构建产物存在时挂载（Task 5 之后才会有 web/dist）
import os
if os.path.isdir("web/dist"):
    app.mount("/", StaticFiles(directory="web/dist", html=True), name="static")
```

- [ ] **Step 5: 运行确认通过**

```bash
cd c:/Users/86159/PycharmProjects/SQLanalysis; python -m pytest tests/test_api_tasks.py -q
```
Expected: 7 passed

- [ ] **Step 6: 全量回归**

```bash
cd c:/Users/86159/PycharmProjects/SQLanalysis; python -m pytest tests -q
```
Expected: 全部通过（55 + 3 + 7）

---

### Task 3: chart_spec v1 与移除 matplotlib

**Files:**
- Modify: `viz/chart.py`
- Test: `tests/test_chart_spec.py`
- Modify: `requirements.txt`（移除 matplotlib）

**Interfaces:**
- Produces `viz.chart.build_chart_spec(df, plan) -> dict`，新增 `series: list[str]`（Task 5 前端消费）

- [ ] **Step 1: 写失败测试**

```python
# tests/test_chart_spec.py
import pandas as pd

from viz.chart import build_chart_spec


def _df():
    return pd.DataFrame({
        "channel": ["线上", "线下"],
        "sales_amount": [10.0, 20.0],
        "order_count": [1, 2],
    })


def test_series_uses_plan_metrics_when_present():
    spec = build_chart_spec(_df(), {"chart_type": "bar", "metrics": ["sales_amount", "order_count"]})
    assert spec["series"] == ["sales_amount", "order_count"]
    assert spec["x"] == "channel"


def test_series_falls_back_to_metric_column():
    spec = build_chart_spec(_df(), {"chart_type": "bar"})
    assert spec["series"] == ["sales_amount"]


def test_no_numeric_column_yields_none():
    spec = build_chart_spec(pd.DataFrame({"channel": ["a"]}), {"chart_type": "bar"})
    assert spec["chart_type"] == "none"
    assert spec["series"] == []


def test_pie_keeps_single_series():
    spec = build_chart_spec(_df(), {"chart_type": "pie"})
    assert spec["chart_type"] == "pie" and len(spec["series"]) == 1


def test_build_chart_figure_removed():
    import viz.chart as chart
    assert not hasattr(chart, "build_chart_figure")
```

- [ ] **Step 2: 运行确认失败**

```bash
cd c:/Users/86159/PycharmProjects/SQLanalysis; python -m pytest tests/test_chart_spec.py -q
```
Expected: FAIL（`series` KeyError）

- [ ] **Step 3: 改 `viz/chart.py`**

保留 `build_chart_spec`，按以下逻辑改写；删除 `build_chart_figure` 及文件顶部的 `matplotlib.pyplot` 导入与 `plt.rcParams` 设置：

```python
from typing import Any, Dict

import pandas as pd

from core.columns import pick_dimension_column, pick_metric_column


def build_chart_spec(result_df: pd.DataFrame, analysis_plan: Dict[str, Any]) -> Dict[str, Any]:
    chart_type = analysis_plan.get("chart_type", "none")
    title = analysis_plan.get("goal", "Analysis Chart")

    x = pick_dimension_column(result_df, analysis_plan)
    y = pick_metric_column(result_df, analysis_plan)

    numeric_cols = result_df.select_dtypes(include="number").columns.tolist()
    metrics = [m for m in (analysis_plan.get("metrics") or []) if m in numeric_cols]
    series = metrics or ([y] if y else [])

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
```

- [ ] **Step 4: 运行确认通过**

```bash
cd c:/Users/86159/PycharmProjects/SQLanalysis; python -m pytest tests/test_chart_spec.py -q; python -m pytest tests -q
```
Expected: 5 passed；全量通过

- [ ] **Step 5: 移除依赖**

`requirements.txt` 中删除 `matplotlib` 行。

---

### Task 4: 删除 Streamlit 前端

**Files:**
- Delete: `app.py`、`.streamlit/`
- Modify: `tests/test_smoke_import.py`、`README.md`

- [ ] **Step 1: 删除文件**

```bash
cd c:/Users/86159/PycharmProjects/SQLanalysis; Remove-Item -Force app.py; Remove-Item -Recurse -Force .streamlit
```

- [ ] **Step 2: 改冒烟测试**

```python
# tests/test_smoke_import.py
def test_import_current_tree():
    import agent.graph
    import analysis.report
    import analysis.memory
    import executors
    import safety.sandbox
    import server.main
    import viz.chart

    executors.init_executors()
    agent.graph.build_graph()
    assert set(executors.registry.list_executors()) >= {"pandas", "sql"}
```

- [ ] **Step 3: 运行**

```bash
cd c:/Users/86159/PycharmProjects/SQLanalysis; python -m pytest tests -q
```
Expected: 全部通过

- [ ] **Step 4: README 更新运行段**

把「本地运行」改为：

```bash
uvicorn server.main:app --reload --port 8000   # 后端 API
cd web && npm run dev                          # 前端 http://localhost:5173
python -m pytest tests -q
```

---

### Task 5: Vue 脚手架 + 前端接线

**Files:**
- Create: `web/`（Vite 工程）、`web/src/api/tasks.ts`、`web/src/types.ts`、`web/src/stores/task.ts`、`web/src/utils/echarts.ts`、`web/src/components/*.vue`、`web/src/views/AnalysisPage.vue`、`web/src/App.vue`、`web/src/main.ts`
- Test: `web/src/utils/echarts.spec.ts`（Vitest）

**Interfaces:**
- Consumes: Task 2 定义的 5 个接口与 `TaskView` 字段名；Task 3 的 `chart_spec v1`
- Produces: 可运行的 SPA；`web/dist` 供 FastAPI 挂载（Task 6）

- [ ] **Step 1: 初始化工程**

```bash
cd c:/Users/86159/PycharmProjects/SQLanalysis; npm create vite@latest web -- --template vue-ts; cd web; npm install; npm install element-plus echarts pinia axios; npm install -D vitest
```

- [ ] **Step 2: `vite.config.ts` 代理**

```ts
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5173,
    proxy: {
      '/api': { target: 'http://127.0.0.1:8000', changeOrigin: true },
    },
  },
})
```

- [ ] **Step 3: 写失败测试（纯函数映射）**

```ts
// web/src/utils/echarts.spec.ts
import { describe, expect, it } from 'vitest'
import { chartSpecToOption } from './echarts'

const rows = [
  { channel: '线上', sales_amount: 10 },
  { channel: '线下', sales_amount: 20 },
]

describe('chartSpecToOption', () => {
  it('bar: x 为类目轴，series 取 spec.series', () => {
    const option = chartSpecToOption(
      { chart_type: 'bar', x: 'channel', y: 'sales_amount', series: ['sales_amount'], title: 't' },
      rows,
    )
    expect(option.series[0].type).toBe('bar')
    expect(option.xAxis.data).toEqual(['线上', '线下'])
    expect(option.series[0].data).toEqual([10, 20])
  })

  it('pie: data 为 {name,value}', () => {
    const option = chartSpecToOption(
      { chart_type: 'pie', x: 'channel', y: 'sales_amount', series: ['sales_amount'], title: 't' },
      rows,
    )
    expect(option.series[0].data[0]).toEqual({ name: '线上', value: 10 })
  })

  it('hist: 对数值列分箱', () => {
    const option = chartSpecToOption(
      { chart_type: 'hist', x: null, y: 'sales_amount', series: ['sales_amount'], title: 't' },
      [{ sales_amount: 1 }, { sales_amount: 2 }, { sales_amount: 3 }],
    )
    expect(option.series[0].type).toBe('bar')
    expect(option.series[0].data.length).toBeGreaterThan(0)
  })

  it('none / 空数据返回 null', () => {
    expect(chartSpecToOption({ chart_type: 'none', x: 'a', y: 'b', series: [], title: '' }, rows)).toBeNull()
    expect(chartSpecToOption({ chart_type: 'bar', x: 'channel', y: 'sales_amount', series: ['sales_amount'], title: '' }, [])).toBeNull()
  })
})
```

- [ ] **Step 4: 运行确认失败**

```bash
cd c:/Users/86159/PycharmProjects/SQLanalysis/web; npx vitest run src/utils/echarts.spec.ts
```
Expected: FAIL，`Cannot find module './echarts'`

- [ ] **Step 5: 实现 `src/utils/echarts.ts`**

```ts
import type { ChartSpec, Row } from '../types'

export function chartSpecToOption(spec: ChartSpec, rows: Row[]): Record<string, any> | null {
  if (!spec || spec.chart_type === 'none' || !rows.length) return null
  const seriesCols = (spec.series || []).filter(Boolean)
  if (!seriesCols.length) return null

  const title = { text: spec.title || '' }

  if (spec.chart_type === 'pie') {
    const col = seriesCols[0]
    return {
      title,
      tooltip: { trigger: 'item' },
      series: [
        {
          type: 'pie',
          radius: '60%',
          data: rows.map((r) => ({ name: String(r[spec.x ?? ''] ?? ''), value: Number(r[col]) || 0 })),
        },
      ],
    }
  }

  if (spec.chart_type === 'hist') {
    const values = rows.map((r) => Number(r[seriesCols[0]])).filter((v) => Number.isFinite(v))
    if (!values.length) return null
    const min = Math.min(...values)
    const max = Math.max(...values)
    const bins = Math.max(1, Math.ceil(Math.log2(values.length) + 1))
    const width = (max - min) / bins || 1
    const counts = new Array(bins).fill(0)
    values.forEach((v) => {
      const idx = Math.min(bins - 1, Math.floor((v - min) / width))
      counts[idx] += 1
    })
    return {
      title,
      tooltip: {},
      xAxis: { type: 'category', data: counts.map((_, i) => `${(min + i * width).toFixed(2)}`) },
      yAxis: { type: 'value' },
      series: [{ type: 'bar', data: counts }],
    }
  }

  // bar / line
  return {
    title,
    tooltip: { trigger: 'axis' },
    xAxis: { type: 'category', data: rows.map((r) => String(r[spec.x ?? ''] ?? '')) },
    yAxis: { type: 'value' },
    series: seriesCols.map((col) => ({
      name: col,
      type: spec.chart_type === 'line' ? 'line' : 'bar',
      data: rows.map((r) => Number(r[col]) || 0),
    })),
  }
}
```

- [ ] **Step 6: 运行确认通过**

```bash
cd c:/Users/86159/PycharmProjects/SQLanalysis/web; npx vitest run src/utils/echarts.spec.ts
```
Expected: 4 passed

- [ ] **Step 7: 类型与接口封装**

`src/types.ts`：

```ts
export type Row = Record<string, any>

export interface ChartSpec {
  chart_type: 'bar' | 'line' | 'pie' | 'hist' | 'none'
  x: string | null
  y: string | null
  series: string[]
  title: string
}

export interface Approval {
  kind: string
  title: string
  content: string
  language: 'sql' | 'python'
}

export type TaskStatus = 'running' | 'awaiting_approval' | 'completed' | 'failed'

export interface TaskView {
  task_id: string
  thread_id: string
  status: TaskStatus
  tool: string
  plan: Record<string, any>
  approval: Approval | null
  artifact_kind: string
  artifact_code: string
  rows: Row[]
  chart_spec: ChartSpec
  insights: string[]
  report: string
  trace: Record<string, any>[]
  logs: string[]
  memory: Record<string, any>
  error: string
}
```

`src/api/tasks.ts`（axios，baseURL 为空走 vite 代理）：

```ts
import axios from 'axios'
import type { TaskView } from '../types'

const http = axios.create({ baseURL: '/api' })

export async function uploadFile(file: File) {
  const form = new FormData()
  form.append('file', file)
  const { data } = await http.post('/files', form)
  return data as { file_id: string; filename: string; source_type: string }
}

export async function createTask(payload: {
  file_id: string
  question: string
  followup?: boolean
  memory?: Record<string, any> | null
}) {
  const { data } = await http.post('/tasks', payload)
  return data as { task_id: string; status: string }
}

export async function getTask(taskId: string) {
  const { data } = await http.get(`/tasks/${taskId}`)
  return data as TaskView
}

export async function resumeTask(taskId: string, approved: boolean) {
  const { data } = await http.post(`/tasks/${taskId}/resume`, { approved })
  return data as { task_id: string; status: string }
}
```

- [ ] **Step 8: Pinia store（轮询 + 状态机）**

`src/stores/task.ts`：

```ts
import { defineStore } from 'pinia'
import { ref } from 'vue'
import { createTask, getTask, resumeTask } from '../api/tasks'
import type { TaskView } from '../types'

export const useTaskStore = defineStore('task', () => {
  const task = ref<TaskView | null>(null)
  const polling = ref(false)
  let timer: number | undefined

  function stopPolling() {
    polling.value = false
    if (timer) window.clearInterval(timer)
    timer = undefined
  }

  function startPolling() {
    if (timer) return
    polling.value = true
    timer = window.setInterval(async () => {
      if (!task.value) return stopPolling()
      try {
        task.value = await getTask(task.value.task_id)
      } catch {
        stopPolling()
        return
      }
      if (task.value.status !== 'running') stopPolling()
    }, 2000)
  }

  async function submit(fileId: string, question: string, followup = false) {
    const created = await createTask({
      file_id: fileId,
      question,
      followup,
      memory: followup ? task.value?.memory ?? null : null,
    })
    task.value = { ...(task.value as any), task_id: created.task_id, status: 'running' }
    startPolling()
  }

  async function decide(approved: boolean) {
    if (!task.value) return
    await resumeTask(task.value.task_id, approved)
    task.value = { ...task.value, status: 'running' }
    startPolling()
  }

  return { task, polling, submit, decide, stopPolling }
})
```

- [ ] **Step 9: 组件与页面**

- `FileUpload.vue`：`el-upload`，`accept=".csv,.xlsx,.xls,.sqlite,.db"`，成功后 emit `file_id`
- `QuestionInput.vue`：`el-input` + 「开始分析」「继续追问」两个 `el-button`
- `ApprovalCard.vue`：`el-dialog`；`language==='sql'` 用 `<pre><code class="language-sql">`，否则 `python`；底部「批准执行」「拒绝执行」
- `ResultTable.vue`：`el-table`，列由 `rows[0]` 的 key 动态生成
- `ChartView.vue`：`chartSpecToOption(spec, rows)` → `echarts.init` 渲染；`option===null` 时不渲染
- `InsightList.vue`：insights 列表 + report 段落
- `TraceTimeline.vue`：`el-collapse` 展示 `trace` 的 `stage/status/detail`
- `AnalysisPage.vue`：串联上传 → 提问 → 审批 → 结果；`status==='failed'` 时 `ElMessage.error(error)`

- [ ] **Step 10: 构建验证**

```bash
cd c:/Users/86159/PycharmProjects/SQLanalysis/web; npm run build
```
Expected: 构建成功并产出 `web/dist`

---

### Task 6: Docker 多阶段构建与文档收尾

**Files:**
- Modify: `Dockerfile`、`docker-compose.yml`、`.dockerignore`、`README.md`

- [ ] **Step 1: Dockerfile 改为多阶段**

```dockerfile
FROM node:22-slim AS web-build
WORKDIR /web
COPY web/package*.json ./
RUN npm ci
COPY web/ ./
RUN npm run build

FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 MPLCONFIGDIR=/tmp/matplotlib
WORKDIR /app
COPY requirements.txt ./
RUN pip install -r requirements.txt
COPY server/ ./server/
COPY service.py agent/ executors/ core/ safety/ llm/ analysis/ viz/ loaders/ ./
COPY --from=web-build /web/dist ./web/dist
RUN useradd -m appuser && chown -R appuser:appuser /app
USER appuser
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD python -c "import sys, urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4).status == 200 else 1)"
CMD ["uvicorn", "server.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

注：图表改由浏览器渲染，镜像不再需要 `fonts-noto-cjk`（原先为 matplotlib 中文准备）。

- [ ] **Step 2: compose 端口改 8000**

`docker-compose.yml`：`ports: - "8000:8000"`，其余（env_file、restart、replicas）不变。

- [ ] **Step 3: `.dockerignore` 排除 node_modules**

追加两行：`web/node_modules/`、`web/dist/`。

- [ ] **Step 4: README 收尾**

更新「运行 / Docker / 包结构」三节：后端 `uvicorn server.main:app`、前端 `web/`、接口表（5 个）、chart_spec v1 字段说明、删除 Streamlit 相关描述。

- [ ] **Step 5: 整体验证**

```bash
cd c:/Users/86159/PycharmProjects/SQLanalysis; python -m pytest tests -q; cd web; npx vitest run
```
Expected: Python 全量通过 + Vitest 4 passed

## Self-Review 结论

- Spec 覆盖：§4 结构 → Task 1/2/5；§5 接口与状态机 → Task 2；§6 chart_spec v1 → Task 3；§7 前端结构与交互 → Task 5；§8 清理与 Docker → Task 4/6；§9 测试 → 各任务内嵌；§10 顺序 → 六任务顺序一致；§11 风险 → Task 2（404 停止轮询）、Task 1（临时文件清理时机）、Task 5（模型可用性由 env 保证）。
- 类型一致性：`TaskView` 字段在 `server/schemas.py`、`web/src/types.ts`、测试断言中三处完全一致；`chart_spec.series` 在 `viz/chart.py` 与 `echarts.ts` 中同名。
- 无占位符：所有代码步骤均为可直接执行的完整代码块。
