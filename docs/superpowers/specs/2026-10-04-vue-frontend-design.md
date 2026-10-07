# DataPilot 前端改为 Vue 的设计

日期：2026-10-04
状态：待审阅
范围：把 Streamlit 前端替换为 Vue3 SPA，后端新增 FastAPI 薄 API 层；`service.py` 及以下各层保持不变。

---

## 1. 背景与目标

当前前端是 Streamlit（`app.py`），直接消费 `service.py` 的 `RunResult` DTO。改为 Vue 的动机是界面可控性与交互能力（审批对话框、可交互图表、多轮对话体验）。

关键约束（决定设计形态）：

1. 一次分析耗时 20–40 秒（多次 LLM 调用 + 代码执行）。
2. 链路会**中途中断等待人工审批**（`status = awaiting_approval`），之后通过 `resume(thread_id, approved)` 继续。因此纯同步的"请求-响应"无法表达"半完成"状态。
3. 会话依赖 `thread_id` + `InMemorySaver`，只在单进程内有效；执行器注册表是进程级全局。

目标：前端完全不感知 LangGraph，只消费 HTTP 接口；后端新增的 API 层是 `service.py` 的薄封装，不复制业务规则。

## 2. 决策记录

| 决策 | 结论 |
|---|---|
| 并发形态 | 单进程实现，但接口按异步任务语义设计（task_id + 状态查询 + resume），将来替换存储层即可支持多人 |
| 前端栈 | Vue3 + TypeScript + Vite + Element Plus + ECharts，工程放 `web/` |
| 图表 | 前端 ECharts 渲染；`chart_spec` 扩到 v1；删除 matplotlib 绘图 |
| Streamlit | 删除 `app.py`、`.streamlit/`、streamlit 依赖 |

## 3. 非目标（YAGNI）

- 不做任务队列（Celery/RQ）、不做 Redis、不做持久化 checkpoint。
- 不做 SSE/WebSocket 推送，前端用轮询（接口预留 `/events` 位置）。
- 不做用户登录/权限、不做多租户。
- 不做组件级前端测试，只测 `chartSpec → ECharts option` 映射函数。
- 不改动 `service.py`、`agent/`、`executors/` 的任何业务规则。
- 不支持"取消正在执行的任务"（`DELETE` 仅做任务记录与临时文件清理）。

## 4. 目标结构

```
server/                    FastAPI 薄 API 层（新增）
  main.py                  FastAPI 应用、CORS、/api/health、挂载 web/dist 静态资源
  api/tasks.py             任务路由
  schemas.py               Pydantic 请求/响应模型
  task_store.py            内存任务存储（接口按 Redis 语义设计）
  files.py                 上传落盘，复用 core.files.detect_source_type
web/                       Vue3 SPA（新增）
  vite.config.ts           dev 代理 /api -> http://localhost:8000
  src/api/tasks.ts         5 个接口封装
  src/stores/task.ts       Pinia：任务状态机 + 轮询
  src/views/AnalysisPage.vue
  src/components/          FileUpload / QuestionInput / ApprovalCard /
                           ResultTable / ChartView / InsightList / TraceTimeline
service.py                 不变
viz/chart.py               只保留 build_chart_spec，删除 build_chart_figure
app.py                     删除
.streamlit/                删除
```

## 5. 后端接口契约

```
POST   /api/files                     multipart 上传 -> {file_id, filename, source_type}
POST   /api/tasks                     {file_id, question, followup?, memory?} -> {task_id, status}
GET    /api/tasks/{task_id}           -> TaskView
POST   /api/tasks/{task_id}/resume    {approved: bool} -> TaskView
DELETE /api/tasks/{task_id}           清理任务记录与临时文件
GET    /api/health                    -> {status: "ok"}
GET    /api/tasks/{task_id}/events    预留，本阶段不实现（返回 501）
```

状态机：`running → awaiting_approval → running → completed | failed`。

- `POST /api/tasks` 把 `service.start_analysis(...)` 提交到 `ThreadPoolExecutor`，立即返回 `task_id`，不阻塞事件循环。
- 前端对 `GET /api/tasks/{id}` 轮询，间隔 2 秒，直到 `status` 为 `completed` / `failed` / `awaiting_approval` 停止（后两者等待用户操作）。
- `POST .../resume` 调用 `service.resume(thread_id, approved)`，同样提交线程池。
- 任务执行抛异常时：记录 `status=failed`、`error=str(e)`，不向前端抛 5xx（业务失败用状态表达）。

`TaskView` 字段（与 `service.RunResult` 一一对应，不得新增业务字段）：

```python
class Approval(BaseModel):
    kind: str
    title: str
    content: str
    language: str            # sql | python


class TaskView(BaseModel):
    task_id: str
    thread_id: str
    status: str              # running | awaiting_approval | completed | failed
    tool: str = ""
    plan: dict = {}
    approval: Optional[Approval] = None
    artifact_kind: str = ""
    artifact_code: str = ""
    rows: List[dict] = []
    chart_spec: dict = {}
    insights: List[str] = []
    report: str = ""
    trace: List[dict] = []
    logs: List[str] = []
    memory: dict = {}
    error: str = ""
```

`task_store.py` 抽象为 `get / set / delete / list` 四个方法，当前用内存字典实现；替换为 Redis 时只需换实现，路由不动。

## 6. 数据契约：chart_spec v1

```jsonc
{
  "chart_type": "bar",         // bar | line | pie | hist | none
  "x": "channel",              // 维度列
  "y": "sales_amount",         // 主指标（保留以兼容现有逻辑）
  "series": ["sales_amount"],  // 数值列（多指标时多个）
  "title": "各渠道销售额"
}
```

后端改动（`viz/chart.py`）：

- `build_chart_spec` 返回值增加 `series` 字段：优先取 `analysis_plan.metrics` 中存在于结果列的项，否则用 `pick_metric_column` 的结果；
- 删除 `build_chart_figure`；
- `chart_type == "none"` 或 `series` 为空时，前端不渲染图表。

前端映射规则：

| chart_type | ECharts option |
|---|---|
| `bar` / `line` | `xAxis.type='category'` 取 `x` 列；每个 `series[i]` 一条 series |
| `pie` | `series[].data = rows.map(r => ({ name: r[x], value: r[series[0]] }))` |
| `hist` | 前端对 `series[0]` 数值列做等宽分箱（sturges 规则），渲染为 bar |
| `none` | 不渲染 |

## 7. 前端结构

```
web/
  index.html
  vite.config.ts              proxy: /api -> http://localhost:8000
  src/main.ts                 createApp + ElementPlus + Pinia
  src/App.vue
  src/api/tasks.ts            uploadFile / createTask / getTask / resumeTask / deleteTask
  src/types.ts                TaskView / ChartSpec 的 TS 类型（与后端 Pydantic 对齐）
  src/stores/task.ts          Pinia：taskId、轮询定时器、状态机、memory 保存
  src/views/AnalysisPage.vue  组合各组件
  src/components/
    FileUpload.vue            el-upload，上传后展示文件名与类型
    QuestionInput.vue         问题输入 +「开始分析」「继续追问」两个按钮
    ApprovalCard.vue          审批：展示 SQL/代码（按 language 高亮）+ 批准/拒绝
    ResultTable.vue           el-table 渲染 rows
    ChartView.vue             ECharts（chart_spec + rows）
    InsightList.vue           关键发现 + 汇报结论
    TraceTimeline.vue         折叠展示 trace 步骤与状态
  src/utils/echarts.ts        chartSpecToOption(spec, rows) 纯函数
```

交互流程：

1. 上传文件 → 拿到 `file_id`；
2. 输入问题 → `POST /api/tasks` → 轮询；
3. `status=awaiting_approval` 时展示 `ApprovalCard`（SQL 显示 `language=sql`，代码显示 `language=python`）；
4. 批准/拒绝 → `POST .../resume` → 继续轮询至终态；
5. 终态展示表格、图表、洞察、结论、trace；失败时展示 `error`。

多轮追问：前端保存上一轮 `TaskView.memory`，点「继续追问」时随请求回传 `followup=true, memory=...`；后端透传给 `service.start_analysis`。

## 8. 清理与依赖变更

- 删除：`app.py`、`.streamlit/`、`viz/chart.py` 中的 `build_chart_figure`。
- `requirements.txt`：移除 `streamlit`、`matplotlib`；新增 `fastapi`、`uvicorn[standard]`、`python-multipart`。
- `Dockerfile` 改多阶段构建：
  1. `node:22-slim` 阶段：`web/` 下 `npm ci && npm run build` → `web/dist`；
  2. `python:3.11-slim` 阶段：安装 Python 依赖，拷贝 `server/ service.py agent/ executors/ ...` 与 `web/dist`，以非 root 用户运行 `uvicorn server.main:app --host 0.0.0.0 --port 8000`；
  3. 健康检查改为 `GET /api/health`；CJK 字体不再需要（图表由浏览器渲染），可从镜像中移除 `fonts-noto-cjk`。
- `docker-compose.yml`：端口 `8000:8000`（生产访问前端静态资源）；开发态前端另起 `npm run dev`（5173）。

## 9. 测试

后端（`pytest` + `fastapi.testclient`）：

- `POST /api/files` 上传 csv/xlsx/sqlite 返回正确 `source_type`；
- `POST /api/tasks` 返回 `running` 且 `task_id` 非空；测试内用 FakeExecutor + monkeypatch（沿用 `tests/test_service.py` 的做法），轮询 `GET /api/tasks/{id}` 最多 20 次、每次间隔 100ms 直到离开 `running`；
- 审批路径：注入 FakeExecutor（复用现有 `tests/test_service.py` 的 Fake）跑到 `awaiting_approval`，`resume(approved=True)` 后为 `completed`；
- 拒绝路径：`resume(approved=False)` 后为 `failed` 且不再返回 `approval`；
- 失败路径：LLM/执行抛错 → `status=failed`，`error` 非空，接口返回 200。

前端（`Vitest`）：

- `chartSpecToOption`：bar/line/pie/hist/none 五种映射，空 rows 不抛错。

已有 55 条 Python 测试必须保持通过；删除 `app.py` 后，原 `tests/test_smoke_import.py` 改为导入 `server.main`。

## 10. 实施顺序

1. `server/` API 层 + 依赖，用 TestClient 验证（此时尚无前端）；
2. `chart_spec` v1 扩展 + 删除 `build_chart_figure` + 移除 matplotlib；
3. 删除 `app.py`、`.streamlit/`、streamlit 依赖；
4. `web/` 脚手架与页面接线；
5. Dockerfile 多阶段改造 + compose 端口调整；
6. 补测试。

## 11. 风险与验收

风险：

1. **轮询期间的孤儿任务**：进程重启后内存任务丢失，前端轮询 404 → 约定返回 404 时前端停止轮询并提示"会话已失效"。
2. **上传临时文件**：沿用 `core.files.save_upload_to_temp`。**任务到达终态时不得删除临时文件**——多轮追问会用同一个 `file_id` 重新发起任务。只在两种时机清理：`DELETE /api/tasks/{id}` 显式清理，以及同一会话上传新文件时清理上一个（沿用 `core.files.delete_temp_file`）。进程重启后的残留靠容器重启清除。
3. **LLM 模型可用性**：`QIANFAN_MODEL` 必须显式配置为账号可用模型（当前默认 `deepseek-v3.2`），否则全链路 401。

验收（需真实 API key）：

1. `uvicorn server.main:app` 启动，`GET /api/health` 返回 ok；
2. 浏览器打开 `http://localhost:8000`，上传 `data/sales.csv`，提问「各渠道销售额排名，给我柱状图和结论」；
3. 弹出审批卡片（Python 代码高亮）→ 点批准 → 出现表格、ECharts 柱状图、洞察与结论；
4. 点拒绝 → 状态为 failed 且不再弹出审批；
5. 继续追问一轮，验证 memory 生效（追问结果沿用上一轮实体）；
6. 上传 `sales_demo.sqlite` 走一遍 SQL 路径，审批卡片语言为 sql。
