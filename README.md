# DataPilot

用自然语言分析数据文件的 Agent 系统。上传 CSV / Excel / SQLite，用中文提问，系统自动完成
**加载数据 → 生成分析计划 → 生成 SQL 或 Python 代码 → 人工审批 → 执行 → 出图 → 出结论**，
并支持多轮追问（通过 memory 承载"这个地区""刚才那个指标"这类指代）。

- 前端：Vue 3 + TypeScript + Vite + Element Plus + ECharts（`web/`）
- 后端：FastAPI（`server/`）+ LangGraph 编排（`agent/`）
- 执行引擎：pandas / SQL / dask（`executors/`），按数据源与数据规模自动选择

---

## 1. 快速开始

### 1.1 本地运行（后端 + 前端两个进程）

```powershell
cd c:\Users\86159\PycharmProjects\SQLanalysis

# ① 安装 Python 依赖
pip install -r requirements.txt

# ② 配置密钥
cp .env.example .env        # 编辑 .env，填入 KIMI_API_KEY

# ③ 启动后端（终端 1）
uvicorn server.main:app --reload --port 8000

# ④ 启动前端（终端 2）
cd web
npm install
npm run dev                 # http://localhost:5173
```

只想验证接口、不启前端：打开 `http://localhost:8000/docs` 看 Swagger。
前端已构建过（`web/dist` 存在）时，FastAPI 会直接挂载静态资源，访问 `http://localhost:8000` 即为前端页面。

### 1.2 Docker 运行

```powershell
cp .env.example .env            # 填入 KIMI_API_KEY
docker compose up -d --build
docker compose logs -f datapilot
# http://localhost:8000
docker compose down             # 停止
```

镜像是**多阶段构建**：`node:22-slim` 阶段构建 `web/dist`，`python:3.11-slim` 阶段运行 uvicorn；
非 root 用户运行；健康检查用 `GET /api/health`。

---

## 2. 环境变量

写在 `.env`（已被 `.gitignore` / `.dockerignore` 排除）或直接注入环境。

| 变量 | 说明 | 默认值 |
|---|---|---|
| `KIMI_API_KEY` | **必需**。缺失时 `get_llm()` 直接抛错 | — |
| `KIMI_BASE_URL` | 模型服务地址 | `https://api.moonshot.cn/v1` |
| `KIMI_MODEL` | 模型名。**平台会上下架模型，务必显式配置** | `kimi-k2-0905-preview` |
| `DASK_ROW_THRESHOLD` | 超过该行数优先选 dask（与 planner 提示词一致） | `50000` |
| `CODE_APPROVAL_ENABLED` | 生成的代码/SQL 是否需人工审批后才执行 | `true` |
| `MAX_RESULT_ROWS` | 执行结果截断行数 | `200` |
| `DEFAULT_MAX_RETRIES` | 单轮最大修复次数 | `1` |
| `MAX_FOCUS_ENTITIES` | memory 中保留的关注实体数上限 | `5` |
| `LLM_MAX_RETRIES` | LLM 调用遇 429/5xx 时的最大重试次数（0 = 关闭） | `4` |
| `LLM_RETRY_BASE_DELAY` | 重试退避基数（秒），按 2 的幂递增 | `2.0` |
| `LLM_RETRY_MAX_DELAY` | 单次等待上限（秒） | `30.0` |
| `CODE_EXEC_TIMEOUT` | 子进程执行代码的超时秒数，超时强制 kill | `30.0` |
| `CODE_EXEC_MEM_LIMIT_MB` | 子进程虚拟内存上限（MB），仅 Linux 生效 | `1024` |
| `CODE_EXEC_CPU_TIME` | 子进程 CPU 时间上限（秒），仅 Linux 生效 | `30` |
| `DUCKDB_MEMORY_LIMIT` | DuckDB 单连接内存上限，防大查询 OOM | `2GB` |
| `DUCKDB_THREADS` | DuckDB 单连接并发线程数，防 CPU 耗尽 | `4` |
| `DUCKDB_STATEMENT_TIMEOUT` | DuckDB 单语句超时，防长查询挂死 | `30s` |

`.env.example` 提供了模板。

---

## 3. 目录结构

```
server/                 FastAPI 薄 API 层
  main.py               应用装配、CORS、/api/health、挂载 web/dist
  api/tasks.py          任务路由（线程池执行、epoch 防过期写回）
  schemas.py            Pydantic 模型：TaskView / Approval / 请求体
  task_store.py         内存任务存储（接口按 Redis 语义：get/set/delete/list）
  files.py              上传落盘（UploadStore）
web/                    Vue3 SPA
  src/api/tasks.ts      HTTP 接口封装
  src/types.ts          TaskView / ChartSpec 的 TS 类型（与后端对齐）
  src/stores/task.ts    Pinia：状态机 + SSE 实时订阅
  src/utils/echarts.ts  chartSpec → ECharts option（纯函数，有单测）
  src/utils/chartColumns.ts 图表可选列推导与 chart_spec 编辑（纯函数，有单测）
  src/components/       FileUpload / QuestionInput / ApprovalCard / ChartControls /
                        ResultTable / ChartView / InsightList / TraceTimeline
  src/views/AnalysisPage.vue
service.py              对外门面：AnalysisService（start_analysis / resume）
agent/
  graph.py              图装配
  routing.py            条件边谓词
  state.py              分组子状态 + reducer
  prompts.py            提示词常量
  support/              plan_schema（plan 校验）、tracing（日志/trace 助手）
  nodes/                load / plan / artifact / approval / chart / report / failure
executors/              base / registry / pandas_executor / sql_executor / dask_executor
loaders/                csv / excel / sqlite / schema_inspector
analysis/               report / memory / summarize（调 LLM 的分析能力）
viz/                    chart.py（只产出 chart_spec，不画图）
safety/                 sandbox.py（代码执行沙箱）、sql_guard.py（SQL 校验）、code_runner.py（子进程执行入口）
llm/                    client.py（LLM 客户端）、json_parse.py（JSON 解析）
core/                   config / sanitize / columns / files / schema 摘要
tests/                  后端 pytest（96 条）
eval_runner.py          离线批量评估
```

**依赖方向严格单向**：

```
web → server → service → agent → executors → {analysis, safety, llm, core, loaders}
```

`executors` 不反向依赖 `agent`（提示词由 `init_executors()` 注入）；
`service` 之下各层不知道 HTTP / 前端的存在。

---

## 4. 核心流程

LangGraph 状态图（`agent/graph.py`）：

```
START → load_data → plan_analysis → generate_artifact
                                        ↓(需审批)      ↓(不需审批)
                                    approval        execute_artifact
                                        ↓
                                   execute_artifact → build_chart(可选) → report → END
执行失败且可修复 → repair_artifact → approval → execute_artifact
任意节点失败 → error → END
```

节点职责：

| 节点 | 职责 |
|---|---|
| `load_data` | 读文件、生成 schema 与样本行 |
| `plan_analysis` | 调 LLM 生成分析计划，并用 `coerce_plan` 校验；用 `router.choose_tool` 选执行引擎 |
| `generate_artifact` | 让执行引擎生成 SQL 或代码 |
| `approval` | `interrupt()` 挂起，等待人工批准/拒绝 |
| `execute_artifact` | 执行产物（先检查是否已批准） |
| `repair_artifact` | 执行失败且未达重试上限时，让 LLM 修复 |
| `build_chart` | 依据结果列生成 `chart_spec` |
| `report` | 生成洞察与汇报结论，并更新 memory |
| `error` | 终止节点，输出失败原因 |

审批语义：

- 拒绝执行 = **终止性错误**（`terminal=True`），直接进 `error` 节点，**不会**重新生成再请求审批。
- 生成了不安全 SQL 也是终止性错误。
- 普通执行失败（代码报错）才进入 `repair_artifact`，受 `DEFAULT_MAX_RETRIES` 限制。

---

## 5. 状态模型

`AgentState` 分 7 组，避免"上帝状态"：

```python
state["input"]["user_question"] / ["file_path"] / ["data_source_type"]
state["dataset"]["schema_info"] / ["sample_rows"]
state["plan"]["analysis_plan"] / ["selected_tool"]
state["artifact"]["code"] / ["kind"] / ["approved"] / ["approval_payload"]
state["execution"]["rows"] / ["summary"] / ["retry_count"]
state["output"]["report"] / ["insights"] / ["chart_spec"]
state["run"]["error"] / ["trace"] / ["run_logs"] / ["memory"] / ["terminal"]
```

两类 reducer：

- `merge_group`（其余分组）：浅合并，节点只返回自己负责的字段，未返回的自动保留。
- `merge_run`（`run` 分组）：浅合并 + **只要本次未显式写 `error` 就把 `error` 归零**。

这条规则消灭了"上一轮错误残留导致后续轮次一进来就跳失败节点"的问题。
**约束**：每个节点都必须返回 `run` 分组（通常写 `run_logs`），否则 reducer 不触发。
另外组内同名字段是**替换**语义，`run_logs` / `trace` / `prior_questions` 这类列表需基于 state 拼全量。

---

## 6. HTTP 接口

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/files` | 上传数据源（multipart），返回 `file_id` |
| POST | `/api/tasks` | 提交分析任务，立即返回 `task_id`（后台线程执行） |
| GET | `/api/tasks/{task_id}` | 查询任务状态（SSE 订阅为主，此端点可作降级/手动查询） |
| POST | `/api/tasks/{task_id}/resume` | 审批：`{"approved": true\|false}` |
| DELETE | `/api/tasks/{task_id}` | 删除任务记录并清理其临时文件 |
| GET | `/api/health` | 健康检查 |
| GET | `/api/tasks/{task_id}/events` | SSE 流式推送状态（`text/event-stream`；`data:` 为 `{type:"update",view}` 或 `{type:"gone"}`） |

**状态机**：`running → awaiting_approval → running → completed | failed`

**错误语义**：业务失败用 `status=failed` + `error` 表达，HTTP 仍返回 200；
只有协议级问题才用状态码——`404`（任务/文件不存在）、`409`（任务不在待审批态，或没有可恢复的会话）。

**`TaskView` 字段**：

> 字段以后端 `server/schemas.py` 的 `TaskView` 为单一真源；前端 `web/src/types.ts` 须与之逐一对应，由 `tests/test_taskview_contract.py` 校验，防 schema 漂移。

```jsonc
{
  "task_id": "...", "thread_id": "...",
  "status": "completed",
  "tool": "pandas",
  "plan": { "goal": "...", "metrics": [], "dimensions": [], "filters": {}, "chart_type": "bar" },
  "approval": { "kind": "pandas", "title": "...", "content": "...", "language": "python" } | null,
  "artifact_kind": "pandas", "artifact_code": "result_df = df.groupby(...)",
  "rows": [ { "channel": "线上", "sales_amount": 406140.08 } ],
  "chart_spec": { "chart_type": "bar", "x": "channel", "y": "sales_amount",
                  "series": ["sales_amount"], "title": "各渠道销售额" },
  "insights": ["..."], "report": "...",
  "trace": [ { "stage": "load_data", "status": "ok", "detail": {} } ],
  "logs": ["..."], "memory": { "focus_entities": {}, "last_result": {} },
  "error": ""
}
```

**`chart_spec` v1**：

| 字段 | 含义 |
|---|---|
| `chart_type` | `bar` / `line` / `pie` / `hist` / `none` |
| `x` | 维度列 |
| `y` | 主指标列 |
| `series` | 数值列数组（多指标时多个），前端 ECharts 据此渲染 |
| `title` | 图表标题 |

前端映射：`bar`/`line` → 类目轴 + 每条 series 一根；`pie` → `{name, value}`；
`hist` → 前端对数值列等宽分箱；`none` 或 `rows` 为空 → 不渲染。

`chart_spec` 由 `viz/chart.py` 自动推断；客户可在图表卡片头部手动改 X 轴、Y 轴与图型，
改动只在前端生效（即时重画），不回传后端、不重新执行代码。可选的列仅限当前结果表已有的列。

**curl 示例**：

```bash
# 上传
FILE_ID=$(curl -s -F "file=@data/sales.csv" http://localhost:8000/api/files | python -c "import sys,json;print(json.load(sys.stdin)['file_id'])")

# 建任务
TASK_ID=$(curl -s -X POST http://localhost:8000/api/tasks \
  -H "Content-Type: application/json" \
  -d "{\"file_id\":\"$FILE_ID\",\"question\":\"各渠道销售额排名\"}" | python -c "import sys,json;print(json.load(sys.stdin)['task_id'])")

# 查询
curl -s http://localhost:8000/api/tasks/$TASK_ID

# 批准
curl -s -X POST http://localhost:8000/api/tasks/$TASK_ID/resume \
  -H "Content-Type: application/json" -d '{"approved":true}'
```

---

## 7. 前端说明

| 组件 | 职责 |
|---|---|
| `FileUpload.vue` | `el-upload` 上传，回显文件名与类型；成功/失败回调 `onSuccess/onError` |
| `QuestionInput.vue` | 问题输入 +「开始分析」「基于上次结果继续追问」 |
| `ApprovalCard.vue` | 审批弹窗，按 `language` 展示 SQL 或 Python 代码，批准/拒绝 |
| `ResultTable.vue` | `el-table`，列取所有行的并集 |
| `ChartView.vue` | ECharts 渲染，随窗口 resize 重绘 |
| `ChartControls.vue` | 图表卡片头部的 X 轴 / Y 轴 / 图型下拉 +「恢复默认」，改完即时重画（纯前端，不回传后端） |
| `InsightList.vue` | 关键发现 + 汇报结论 |
| `TraceTimeline.vue` | 折叠展示执行链路每一步与状态 |

交互与状态处理（`src/stores/task.ts`）：

- 提交任务后通过 `EventSource` 订阅 `GET /api/tasks/{id}/events`，收到 `update` 事件即刷新视图（含执行阶段 `stage`，如规划中/生成 SQL/执行中，实时展示当前步骤），终态或 `gone` 事件时关闭流。
- SSE 收到 `gone`（进程重启导致任务丢失）→ 停止并提示"会话已失效"；`onerror` 断线时停止并提示。
- 提交新一轮时重置为空白 `TaskView`，不残留上一轮的 `trace` / `approval`。
- **审批弹窗不可通过遮罩 / ESC / 右上角关闭**——它是 `awaiting_approval` 状态唯一的恢复入口，误关会让任务永久挂起。
- 多轮追问：把上一轮的 `memory` 随请求回传（`followup=true`）。

开发态：`vite.config.ts` 把 `/api` 代理到 `http://127.0.0.1:8000`，前端跑在 5173。

---

## 8. 执行引擎

`executors/` 有三种引擎，通过 `executors/registry.py` 注册，`agent/router.py` 选择：

| 数据源 | 引擎选择规则 |
|---|---|
| SQLite | 强制 SQL |
| CSV / Excel | 行数 ≥ `DASK_ROW_THRESHOLD` 且 dask 可用 → dask；否则按 planner 建议（`pandas`/`dask`）；兜底 pandas |
| CSV（且 planner 选 `duckdb`） | DuckDB 引擎（SQL 类，仅 CSV；未安装时 `init_executors()` 跳过注册，回落 pandas） |
| 未知类型 | `none` → 计划节点直接判失败 |

**引擎契约**：

```python
generate(state) -> {"code": str, "kind": str, "error": str}
repair(state)   -> {"code": str, "kind": str, "error": str, "retry_count": int}
execute(state)  -> {"rows": list, "summary": dict, "error": str, "terminal": bool}
```

`terminal=True` 表示"不可修复的终止性错误"（用户拒绝执行、生成了不安全 SQL），
路由会直接进终止节点而不是重试。

### 新增一个数据源（如 parquet）

1. `loaders/` 增加 `parquet_loader.py`；
2. `core/files.py` 的 `detect_source_type` 增加后缀；
3. 若走 pandas/dask，在对应 executor 的 `load_frame` 加分支；若走 SQL，在 `router.choose_tool` 加硬约束。

### 新增一个执行引擎（如 duckdb）

1. 新建 `executors/duckdb_executor.py`，继承 `CodeExecutor`（生成代码类）或 `BaseExecutor`（SQL 类），
   实现 `supports / generate / repair / execute`；
2. `executors/__init__.py` 的 `init_executors()` 中注册，**并注入对应的生成/修复提示词**；
3. `agent/prompts.py` 增加提示词；必要时在 `router.choose_tool` 里加选中规则。

> 本项目已落地一个执行引擎：**DuckDB**（`executors/duckdb_executor.py`，SQL 类）。
> 它用 DuckDB 直接在 CSV 文件上跑只读 SQL（数据注册为表 `data`），生成 SQL 经 `safety/sql_guard.py` 校验，
> 执行在父进程内完成（与 SQLite 执行器同构，不经子进程沙箱）。`choose_tool` 在 planner 选 `duckdb` 且数据源为 CSV 时启用；
> 未安装 `duckdb` 时 `init_executors()` 自动跳过注册。Excel 仍需额外扩展，暂走 pandas。

---

## 9. 安全模型

**代码执行**（`safety/sandbox.py` + `safety/code_runner.py`）：LLM 生成的代码先清洗（去 markdown 代码块、import 行、中文引导语），
再做 AST 静态校验，最后在**独立子进程**中受限执行（父进程通过超时强制 kill）。

被拦截的行为：

- `import` / `from ... import`
- `while` 循环（避免死循环拖死进程）
- 访问 dunder 属性（阻断 `str.__class__.__base__.__subclasses__()` 这类逃逸）
- 危险内置调用：`open` / `eval` / `exec` / `compile` / `__import__` / `getattr` / `setattr` / `globals` / `locals` 等
- 文件与网络 IO 方法：`pd.read_csv` / `df.to_csv` / `read_sql` / `to_json` 等
- 引用 `os` / `sys` / `subprocess` / `socket` / `pickle` 等模块名

每次执行使用独立命名空间（不共享 globals，避免跨请求污染），且运行在独立子进程内（与父进程隔离）。

**资源限制**：Linux 下子进程用 `resource.setrlimit` 限制虚拟内存（`RLIMIT_AS`）与 CPU 时间（`RLIMIT_CPU`）；
Windows 无 `resource` 模块，自动退化为仅超时保护。默认超时 30s，可由 `CODE_EXEC_TIMEOUT` 配置。

**SQL**（SQLite / DuckDB，`safety/sql_guard.py` + 连接层）：

- 只允许 `SELECT` / `WITH ... SELECT`；禁止 `insert/update/delete/drop/alter/truncate` 等关键字；
- SQLite 一律以**只读 URI**（`file://...?mode=ro`）打开，并显式关闭连接；
- DuckDB 在父进程内执行：先物化内存表 `data`，再 `SET enable_external_access=false` 锁死引擎级外部文件访问（即便 `sql_guard` 漏网也读不到别的文件），并通过 `DUCKDB_MEMORY_LIMIT` / `DUCKDB_THREADS` / `DUCKDB_STATEMENT_TIMEOUT` 限制内存、线程与语句超时，防 OOM / CPU 耗尽 / 长查询挂死；
- SQL 类（SQLite、DuckDB）生成后均需人工审批；被拒即终止。

**审批**：默认 `CODE_APPROVAL_ENABLED=true`，代码与 SQL 都要人工批准后才执行；
被拒绝即终止，不会重新生成再申请。设 `CODE_APPROVAL_ENABLED=false` 可关闭（不推荐）。

**容器**：镜像以非 root 用户运行；`.dockerignore` 排除 `.env`；密钥走 `env_file` 注入，不进镜像。

---

## 10. 测试

```powershell
python -m pytest tests -q          # 后端，117 条，不联网
cd web; npm run test               # 前端 Vitest，23 条（ECharts 映射 4 + 图表列候选 19）
cd web; npm run typecheck          # vue-tsc 类型检查
cd web; npm run build              # 构建
```

后端测试覆盖：沙箱拦截（6 类恶意代码）、SQL 校验、JSON 解析兜底、plan 校验、
列/指标选择、报告与 memory、`chart_spec` v1、任务存储、SSE 完整流（订阅/推送/终态关流）、
以及 API 的 成功 / 待审批 / 批准 / 拒绝终止 / 404 / 409 / 501 / service 抛错 等路径。
API 测试用 `FakeExecutor` 与 monkeypatch 拦截 LLM，**不发真实网络请求**。

---

## 11. 离线评估

`eval_runner.py` 批量跑用例并把结果写成 CSV（需要真实 API key）：

```powershell
python eval_runner.py
# 输出 eval_single_turn_results.csv / eval_multi_turn_results.csv
```

- 单轮：5 个用例，校验工具选择（期望 dask）与图表是否产出；
- 多轮：M1 三连问（"退款率最高的地区" → "看看这个地区的销售额" → "再看这个地区的渠道分布并绘制饼状图"），
  重点看 `memory_focus_entities` 是否正确延续。

评估脚本复用 `service`（会自动批准审批中断），用例在文件顶部的 `TEST_CASES` / `MULTI_TURN_CASES`。

---

## 12. 已知限制

- **单进程、单副本**：会话 checkpoint 用 `InMemorySaver`，进程重启即丢失，多副本之间不共享。
  任务状态也在内存里。要横向扩展，需换成 `SqliteSaver`/Redis 并把 `TaskStore` 换成对应实现。
- **任务不可取消**：`DELETE` 只删除记录与临时文件；已在跑的分析无法中断。
- **无鉴权**：没有登录/权限/多租户，适合内网小团队使用。
- **上传临时文件**：落在系统临时目录，`DELETE` 任务或重新上传时才清理；进程异常退出会残留。
- **代码执行已在独立子进程**：带超时（默认 30s，可配 `CODE_EXEC_TIMEOUT`）与 Linux 内存/CPU 限额（见第 9 节）；Windows 仅超时兜底，生产建议部署在 Linux 以获得内存限制。
- **SSE 实时推送**：`GET /api/tasks/{id}/events` 以 `EventSource` 流式推送状态；原 `501` 预留已移除。
- 前端打包体积约 2.1MB（Element Plus + ECharts 占大头），未做代码分割。

---

## 13. 排错

| 现象 | 原因 / 处理 |
|---|---|
| `缺少 KIMI_API_KEY` | 没有 `.env`，或 `.env` 不在项目根目录 |
| `401 invalid_model` | 模型名或地址不可用。**显式设置 `KIMI_MODEL` / `KIMI_BASE_URL`**（可用值需实测，平台会上下架） |
| `403 account_overdue` | 账号欠费，不是代码问题 |
| `429 rate_limit_reached` | 账号配额打满（如 RPM=3）。调大 `LLM_MAX_RETRIES` 自动退避重试，或降低并发 / 换更高配额的 key |
| 任务一直 `running` | 后端线程执行中；查看 `GET /api/tasks/{id}` 的 `trace`，或后端日志 |
| 前端直连 8000 白屏 | 需要先 `cd web && npm run build` 产出 `web/dist` |
| 轮询提示"会话已失效" | 后端进程重启过，任务记录已丢失，重新提交即可 |
| SQLite 打不开 | 路径含空格/`#` 时依赖 `Path.as_uri()` 转义；只读模式下文件必须存在 |
| 图表中文乱码 | 浏览器渲染，一般不会出现；容器部署已不需要 CJK 字体 |

---

## 14. 设计文档

- 结构重整设计：`docs/superpowers/specs/2026-09-21-structure-refactor-design.md`
- 结构重整实施计划：`docs/superpowers/plans/2026-09-21-structure-refactor.md`
- Vue 前端改造设计：`docs/superpowers/specs/2026-10-04-vue-frontend-design.md`
- Vue 前端实施计划：`docs/superpowers/plans/2026-10-04-vue-frontend.md`
- 实施进度台账：`.superpowers/sdd/progress.md`

