# DataPilot 结构重整设计（B 档：长期迭代的内部工具）

日期：2026-09-21
状态：待审阅
范围：只做结构重整与状态模型治理，**不新增业务能力**（不新增数据源、不新增图表类型、不改提示词内容）

---

## 1. 背景与目标

项目定位为**要长期迭代的内部数据分析工具**：会持续增加数据源（更多文件格式/数据库）与分析能力（更多执行引擎、更多图表与结论形态）。

当前结构的问题不是"能不能跑"，而是**变更成本**：

1. 依赖方向成环：`agent` 与 `executors` 互相依赖，改提示词会影响执行器，改执行器要动编排层。
2. 状态模型是扁平的"上帝 State"（30+ 字段、无 reducer），直接制造了 `error` 跨轮残留这类 bug。
3. 包边界模糊：`tools/` 同时装"调 LLM 的分析能力"与"纯函数工具"，且被 `executors` 反向依赖；数据加载职责分裂在 `loaders/` 与 `executors/` 两处。
4. UI 直连内部字段：`app.py` 自行构造 `init_state`、认识 `generated_*` / `chart_ready` / `__interrupt__`；`eval_runner.py` 复制了一份 state 构造逻辑。
5. 无可回归的测试：只有依赖真实 LLM 的端到端 eval，纯逻辑无单测。

目标：让"新增一个数据源 / 新增一种执行引擎 / 改一个状态字段"都只触碰一层，且能被单测覆盖。

---

## 2. 非目标（YAGNI）

- 不引入 DI 框架、不做插件动态发现机制。
- 不做多用户并发隔离、不做持久化 checkpoint（保持 `InMemorySaver`）。
- 不实现 exec 的 CPU/内存/超时硬限制（仍是同进程执行，文档注明生产需子进程化）。
- 不重写提示词内容、不调整分析链路的节点顺序。
- 不引入 pydantic 等运行时校验框架（用轻量 `coerce_plan` 函数）。

---

## 3. 目标结构

```
app.py                  只做 UI：表单 + 渲染 ResultDTO，不再认识 AgentState 字段
service.py              唯一对外入口 AnalysisService(start / resume)
eval_runner.py          复用 service，不再自己拼 state

agent/
  graph.py              图装配（START / END / 节点注册）
  routing.py            条件边谓词（after_plan / after_generate / after_approval / after_execute / after_repair / after_build_chart）
  state.py              分组子状态（合并并删除 schemas.py）
  support/
    tracing.py          append_log / append_trace
    plan_schema.py      coerce_plan()：LLM 输出 -> 受校验的 AnalysisPlan
  nodes/
    load.py             load_data_node
    plan.py             plan_analysis_node
    artifact.py         generate_artifact_node / repair_artifact_node / execute_artifact_node
    approval.py         approval_node
    chart.py            build_chart_node
    report.py           report_node
    failure.py          error_node
  prompts.py            纯字符串常量，无逻辑

executors/              base.py / registry.py / pandas_executor.py / sql_executor.py / dask_executor.py
                        不再 import agent.prompts，prompt 由构造参数注入
loaders/                csv / excel / sqlite / schema_inspector / frame.py（统一加载入口）
analysis/               report.py / insights.py / memory.py / summarize.py   <- 原 tools/report_tool.py
viz/                    chart.py                                             <- 原 tools/chart_tool.py
safety/                 sandbox.py / sql_guard.py          <- utils/sandbox.py + tools/sql_tool.py
llm/                    client.py / json_parse.py          <- utils/llm.py + utils/safe_json.py
core/                   config.py / sanitize.py / columns.py / files.py / schema.py
tests/                  纯函数单测 + FakeLLM/FakeExecutor 集成测试
```

删除：`agent/schemas.py`（全库无引用，其 `AnalysisPlan` 类型并入 `agent/state.py`）、`tools/` 目录、`utils/` 中的已迁移模块。

`safety/` 提升为一级包：它是本系统的核心风险面（LLM 生成代码执行 + SQL 注入面），埋在 `utils/` 里容易被当作普通工具函数对待。

---

## 4. 状态模型

### 4.1 分组

```python
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
    kind: Literal["sql", "pandas", "dask"]
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
    input: InputState
    dataset: DatasetState
    plan: PlanState
    artifact: ArtifactState
    execution: ExecutionState
    output: OutputState
    run: RunState
```

### 4.2 Reducer

两类 reducer，按分组用途选择：

```python
def merge_group(old, new):
    """普通分组：浅合并，节点未返回的字段保留。"""
    return {**(old or {}), **(new or {})}


def merge_run(old, new):
    """RunState：浅合并，且 error 只要本次未显式设置就归零。"""
    merged = {**(old or {}), **(new or {})}
    merged["error"] = (new or {}).get("error", "")
    return merged
```

`input / dataset / plan / artifact / execution / output` 用 `merge_group`，`run` 用 `merge_run`。

`merge_run` 直接消灭"上一轮 error 残留导致后续每轮一进来就跳 error 节点"的问题：失败节点返回 `{"error": "..."}` 时保留，成功节点不返回 `error` 时自动归零，无需每个节点手动补 `"error": ""`。

### 4.3 字段重命名

- `generated_sql` / `generated_pandas_code` / `generated_dask_code` / `generated_artifact` → 统一为 `artifact.code` + `artifact.kind`。
- `execution_result_rows` → `execution.rows`；`execution_result_summary` → `execution.summary`。
- `final_insights` / `final_report` → `output.insights` / `output.report`。
- 其余字段按 4.1 分组平移，语义不变。

由于 UI 与 eval 改为消费 DTO（第 5 节），这些重命名**不会**扩散到 `app.py`。

---

## 5. Service 门面与 DTO

```python
@dataclass
class PendingApproval:
    kind: str        # sql / pandas / dask
    title: str
    content: str
    language: str    # sql | python

@dataclass
class RunResult:
    thread_id: str
    status: str               # completed | awaiting_approval | failed
    tool: str
    plan: AnalysisPlan
    pending: Optional[PendingApproval]
    artifact_kind: str
    artifact_code: str
    rows: List[Dict[str, Any]]
    chart_spec: Dict[str, Any]
    chart_ready: bool
    insights: List[str]
    report: str
    trace: List[Dict[str, Any]]
    logs: List[str]
    memory: Dict[str, Any]
    error: str

class AnalysisService:
    def __init__(self, graph=None): ...
    def start_analysis(self, file_path, source_type, question, followup=False, memory=None) -> RunResult
    def resume(self, thread_id: str, approved: bool) -> RunResult
```

职责：

- 构造初始 state（唯一的 state 构造入口，`app.py` 与 `eval_runner.py` 不再各写一份）；
- 每次 `start_analysis` 生成新 `thread_id`（新一轮不复用 checkpoint）；
- 统一处理 `__interrupt__`：任意一次 invoke/resume 返回的中断都转成 `pending`；
- 把 `AgentState` 翻译成 `RunResult`，UI 只消费 DTO。

`app.py` 因此不再引用任何 `AgentState` 字段名。

---

## 6. Plan 校验

新增 `agent/support/plan_schema.py`：

```python
ALLOWED_CHART_TYPES = {"line", "bar", "pie", "hist", "none"}
ALLOWED_TOOLS = {"pandas", "sql", "dask"}

def coerce_plan(raw: Any) -> AnalysisPlan:
    # raw 非 dict -> 返回空 plan
    # goal / reason / time_range -> str
    # metrics / dimensions -> list[str]（丢弃非字符串元素）
    # filters -> dict
    # chart_type 不在白名单 -> "none"
    # tool 不在白名单 -> None（由 router 兜底）
    # needs_chart -> bool
```

接入点：`plan_analysis_node` 拿到 LLM 输出后立即 `coerce_plan`，之后 `router`、`chart`、`report`、`memory` 全部消费结构化对象，不再对裸 dict 做防御式 `.get()`。

---

## 7. Executor 解耦

```python
class CodeExecutor(BaseExecutor):
    def __init__(self, generator_prompt: str, repair_prompt: str, artifact_kind: str): ...

# executors/__init__.py
register_executor(PandasExecutor(
    generator_prompt=PANDAS_GENERATOR_PROMPT,
    repair_prompt=PANDAS_REPAIR_PROMPT,
    artifact_kind="pandas",
))
```

- `executors/*` 不再 `import agent.prompts`，`agent` → `executors` 变为单向依赖。
- `executors` 依赖 `analysis.summarize`（单向，`analysis` 不依赖 `executors`）。
- `build_graph(executors=None)` 允许注入执行器列表，测试可用 `FakeExecutor` 替换整个执行层。

---

## 8. 迁移步骤（每步独立可验证）

| # | 内容 | 验证方式 |
|---|---|---|
| 0 | `git init` 并提交基线（当前不在版本管理下，移动文件无回滚点） | `git status` 干净 |
| 1 | POC：嵌套 TypedDict + `merge_group` reducer 在最小图上验证合并与 error 归零行为 | 独立脚本 |
| 2 | 建 `analysis/ viz/ safety/ llm/ core/`，搬移文件；删除 `tools/`、`utils/` 已迁移模块 | `compileall` + `import` |
| 3 | `plan_schema.coerce_plan` + 接入 plan 节点 | 脏输入单测 |
| 4 | state 分组重命名（第 4.3 节）+ 节点改写 | 单测 + 图编译 |
| 5 | `service.py` + `RunResult`，改写 `app.py` / `eval_runner.py` | 两者只依赖 DTO |
| 6 | 拆 `agent/nodes/` 包 + `routing.py` | import + 图编译 |
| 7 | prompt 构造注入 executors | 图编译 + registry 单测 |
| 8 | 补 `tests/` | pytest |

每步完成后运行：`python -m compileall` + 关键模块 import + 已有单测。

---

## 9. 测试策略

纯函数单测（无 LLM、无网络）：

- `tests/test_sandbox.py`：正常 pandas 代码可执行；`import`、dunder 属性链、`while`、文件 IO 方法（`read_csv`/`to_csv` 等）、危险内置调用均被拦截；globals 不被跨执行污染。
- `tests/test_json_parse.py`：纯 JSON / ```json 代码块 / 前后带说明文字 / 尾逗号；非 dict 结果视为解析失败。
- `tests/test_sql_guard.py`：非 SELECT/WITH 拒绝；写操作关键字拒绝；字符串字面量不误杀（可用性）。
- `tests/test_router.py`：sqlite→sql；大表→dask；小表→planner 建议；非法建议→pandas 兜底；未知数据源→none。
- `tests/test_plan_schema.py`：脏 LLM 输出被收敛为合法 plan。
- `tests/test_columns.py`：维度/指标选择优先级、稳定维度判定。
- `tests/test_service.py`：`FakeExecutor` + `FakeLLM` 跑通 start → 审批 → resume（批准/拒绝两条路径），拒绝必须落到 `failed` 而不是再次进入审批。

---

## 10. 风险与验收

风险：

1. **LangGraph 对嵌套 TypedDict + reducer 的支持细节**未知（未锁版本）→ 第 1 步必须做 POC，若不兼容则退回"扁平 state + 显式重置 + 单测守护"。
2. **无法端到端验证**：本环境无 `QIANFAN_API_KEY`，只能保证 import、图编译、纯函数与 Fake 集成测试通过。
3. 大范围文件移动期间短期不可用 → 按步骤提交，随时可回退。

验收标准（由用户在本地执行）：

- `pytest tests/` 全绿；
- `streamlit run app.py` 启动，上传 CSV 走完 分析 → 审批 → 执行 → 图表 → 结论；
- 拒绝审批后流程终止并提示，不再重新弹出审批；
- `python eval_runner.py` 产出与重构前同结构的 CSV（字段可评估、无异常行）。

---

## 11. 保持不动的既有修复

迁移过程中必须保留以下已修复行为，并由单测守护：

- `requirements.txt` 含 `dask` / `numpy`，且 dask 未安装时只禁用 dask 执行器；
- 用户拒绝执行标记 `terminal=True`，路由直达终止，不进入 repair；
- 任意路径（invoke / resume）产生的 `__interrupt__` 都会被转成审批态；
- SQLite 以只读 URI 打开并显式关闭；
- 上传新文件时删除旧临时文件；
- sandbox 的 AST 校验与 IO 方法黑名单；
- dask 阈值 `DASK_ROW_THRESHOLD` 在 router、提示词、eval 期望三处一致。
