# DataPilot 结构重整 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 DataPilot 从"能跑通的分层脚本"重整为依赖单向、状态分组、UI 只消费 DTO 的可长期迭代内部结构，且不丢失既有修复行为。

**Architecture:** 拆出 `core/ safety/ llm/ analysis/ viz/` 五个概念包替代模糊的 `tools/` 与 `utils/`；`AgentState` 改为 7 个分组子状态并配 reducer（`error` 默认归零）；新增 `service.py` 作为唯一对外入口，`app.py` 与 `eval_runner.py` 只消费 `RunResult` DTO；`executors` 通过构造参数接收 prompt，与 `agent` 解环。

**Tech Stack:** Python 3.10+、LangGraph（StateGraph + InMemorySaver + interrupt）、LangChain-OpenAI、pandas、dask（可选）、Streamlit、pytest。

## Global Constraints

- 环境 Windows + PowerShell，命令前缀 `cd c:/Users/86159/PycharmProjects/SQLanalysis;`。
- 无 `QIANFAN_API_KEY`，**测试不得发起真实网络请求**；LLM 一律 monkeypatch 或 Fake。
- 禁止放宽 sandbox 规则；禁止重新引入 `generated_sql / generated_pandas_code / generated_dask_code`。
- 每步完成后运行 `python -m compileall -q .`。
- 不新增/升级运行时依赖（`pytest` 自行安装，不写入 requirements）。
- 不改提示词内容、不改节点执行顺序、不新增业务能力。
- 每个任务结束 `git commit`；项目当前不在 git 管理下，Task 1 建立基线。

---

### Task 1: 建立版本基线与测试环境

**Files:** Create `.gitignore`、Create `tests/test_smoke_import.py`

- [ ] **Step 1: 建基线**

```bash
cd c:/Users/86159/PycharmProjects/SQLanalysis; git init; git add -A; git commit -m "chore: baseline before structure refactor"
```

- [ ] **Step 2: 写 `.gitignore`**

```gitignore
__pycache__/
*.pyc
.pytest_cache/
.env
```

- [ ] **Step 3: 写导入冒烟测试**

```python
# tests/test_smoke_import.py
def test_import_current_tree():
    import agent.graph, executors, tools.chart_tool, tools.report_tool, utils.sandbox
    executors.init_executors()
    agent.graph.build_graph()
    assert set(executors.registry.list_executors()) >= {"pandas", "sql"}
```

- [ ] **Step 4: 运行**

```bash
cd c:/Users/86159/PycharmProjects/SQLanalysis; python -m pytest tests/test_smoke_import.py -q
```
Expected: 1 passed

- [ ] **Step 5: 提交**

```bash
git add .gitignore tests; git commit -m "chore: add baseline import smoke test"
```

---

### Task 2: POC —— 嵌套 TypedDict + reducer 可行性

**Files:** Create `poc_nested_state.py`（验证后删除）

**Interfaces:** 结论供 Task 8 使用。若 LangGraph 支持嵌套分组 + 自定义 reducer → Task 8 按本计划实施；若不支持 → Task 8 改为"扁平 state + `fresh_run_state()` 显式重置 + 单测守护"，其余任务不受影响。

- [ ] **Step 1: 写 POC 脚本**

```python
# poc_nested_state.py
from typing import Annotated, Any, Dict, TypedDict
from langgraph.graph import StateGraph, START, END


def merge_group(old, new):
    return {**(old or {}), **(new or {})}


def merge_run(old, new):
    merged = {**(old or {}), **(new or {})}
    merged["error"] = (new or {}).get("error", "")
    return merged


class S(TypedDict, total=False):
    plan: Annotated[Dict[str, Any], merge_group]
    run: Annotated[Dict[str, Any], merge_run]


def a(state):
    return {"plan": {"goal": "g"}, "run": {"logs": ["a"]}}


def b(state):
    return {"plan": {"tool": "pandas"}, "run": {"error": "boom"}}


def c(state):
    return {"plan": {"chart_type": "bar"}}


g = StateGraph(S)
for name, fn in (("a", a), ("b", b), ("c", c)):
    g.add_node(name, fn)
g.add_edge(START, "a"); g.add_edge("a", "b"); g.add_edge("b", "c"); g.add_edge("c", END)
out = g.compile().invoke({"plan": {}, "run": {}})
print(out)
assert out["plan"] == {"goal": "g", "tool": "pandas", "chart_type": "bar"}, out["plan"]
assert out["run"]["logs"] == ["a"], out["run"]
assert out["run"]["error"] == "", out["run"]
print("POC OK")
```

- [ ] **Step 2: 运行**

```bash
cd c:/Users/86159/PycharmProjects/SQLanalysis; python poc_nested_state.py
```
Expected: `POC OK`（若报 `InvalidUpdateError` 或分组被整体覆盖，记录结论，Task 8 走 fallback 方案）

- [ ] **Step 3: 清理并提交**

```bash
cd c:/Users/86159/PycharmProjects/SQLanalysis; Remove-Item poc_nested_state.py; git add -A; git commit -m "chore: verify nested state reducer feasibility"
```

---

### Task 3: 建立 `core/` 包

**Files:** Create `core/__init__.py`；Move `utils/{config,sanitize,columns,files,schema}.py` → `core/`

**Interfaces:**
- Produces: `core.config`（`DASK_ROW_THRESHOLD` / `MAX_RESULT_ROWS` / `CODE_APPROVAL_ENABLED` / `DEFAULT_MAX_RETRIES` / `MAX_FOCUS_ENTITIES`）、`core.sanitize.make_json_safe`、`core.columns.{pick_dimension_column,pick_metric_column,is_stable_focus_dimension}`、`core.files.{detect_source_type,save_upload_to_temp,delete_temp_file}`、`core.schema.build_schema_summary_for_llm`

- [ ] **Step 1: 搬文件**

```bash
cd c:/Users/86159/PycharmProjects/SQLanalysis; New-Item -ItemType Directory core | Out-Null; New-Item core/__init__.py -ItemType File | Out-Null; git mv utils/config.py core/config.py; git mv utils/sanitize.py core/sanitize.py; git mv utils/columns.py core/columns.py; git mv utils/files.py core/files.py; git mv utils/schema.py core/schema.py
```

- [ ] **Step 2: 替换 import**（仅限这五个模块名）

| 旧 | 新 |
|---|---|
| `from utils.config import` | `from core.config import` |
| `from utils.sanitize import` | `from core.sanitize import` |
| `from utils.columns import` | `from core.columns import` |
| `from utils.files import` | `from core.files import` |
| `from utils.schema import` | `from core.schema import` |

涉及：`agent/nodes.py`、`agent/prompts.py`、`agent/router.py`、`app.py`、`eval_runner.py`、`executors/base.py`、`executors/sql_executor.py`、`tools/chart_tool.py`、`tools/report_tool.py`

- [ ] **Step 3: 验证**

```bash
cd c:/Users/86159/PycharmProjects/SQLanalysis; python -m compileall -q .; python -m pytest tests -q
```
Expected: 编译无输出、1 passed

- [ ] **Step 4: 提交**

```bash
git add -A; git commit -m "refactor: move shared helpers into core package"
```

---

### Task 4: 建立 `safety/` 包 + 安全回归测试

**Files:** Create `safety/{__init__,sandbox,sql_guard}.py`；Test `tests/test_sandbox.py`、`tests/test_sql_guard.py`；Delete `utils/sandbox.py`、`tools/sql_tool.py`

**Interfaces:**
- Consumes: `core.config.MAX_RESULT_ROWS`
- Produces: `safety.sandbox.{clean_code,validate_code,build_safe_globals,normalize_result,run_generated_code}`、`safety.sql_guard.{clean_sql,is_safe_sql,run_sql}`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_sandbox.py
import pandas as pd
import pytest

from safety.sandbox import build_safe_globals, clean_code, run_generated_code, validate_code


def _df():
    return pd.DataFrame({"region": ["a", "b", "a"], "sales_amount": [1, 2, 3]})


def test_normal_code_runs():
    out = run_generated_code(
        "result_df = df.groupby('region', as_index=False)['sales_amount'].sum()",
        {"df": _df(), "pd": pd},
    )
    assert out.to_dict(orient="records") == [
        {"region": "a", "sales_amount": 4},
        {"region": "b", "sales_amount": 2},
    ]


@pytest.mark.parametrize("code", [
    "result_df = df.head(1)\nx = str.__class__.__base__.__subclasses__()",
    "while True:\n    pass\nresult_df = df",
    "result_df = pd.read_csv('C:/secret.csv')",
    "result_df = df.to_csv('C:/out.csv')",
    "result_df = df.head(1)\n__import__('os')",
    "result_df = df.head(1)\nx = os.getcwd()",
])
def test_dangerous_code_blocked(code):
    with pytest.raises(ValueError):
        validate_code(clean_code(code))


def test_globals_not_shared_between_runs():
    g1 = build_safe_globals({"pd": pd})
    g1["leak"] = 1
    assert "leak" not in build_safe_globals({"pd": pd})


def test_result_must_be_assigned():
    with pytest.raises(ValueError):
        run_generated_code("x = 1", {"df": _df(), "pd": pd})
```

```python
# tests/test_sql_guard.py
import sqlite3

import pandas as pd
import pytest

from safety.sql_guard import clean_sql, is_safe_sql, run_sql


def test_select_allowed():
    assert is_safe_sql("SELECT * FROM t LIMIT 10") == (True, "")


def test_with_cte_allowed():
    ok, _ = is_safe_sql("WITH x AS (SELECT 1 AS a) SELECT * FROM x")
    assert ok


@pytest.mark.parametrize("sql", [
    "DELETE FROM t",
    "UPDATE t SET a = 1",
    "DROP TABLE t",
    "WITH x AS (SELECT 1) DELETE FROM t",
])
def test_forbidden_statements_rejected(sql):
    ok, reason = is_safe_sql(sql)
    assert not ok and reason


def test_fenced_sql_is_unwrapped():
    assert clean_sql("```sql\nSELECT 1\n```") == "SELECT 1"


def test_run_sql_returns_dataframe(tmp_path):
    conn = sqlite3.connect(tmp_path / "t.sqlite")
    conn.execute("CREATE TABLE t (a INTEGER)")
    conn.execute("INSERT INTO t VALUES (1)")
    conn.commit()
    df = run_sql(conn, "SELECT * FROM t")
    conn.close()
    assert isinstance(df, pd.DataFrame) and len(df) == 1
```

- [ ] **Step 2: 运行确认失败**

```bash
cd c:/Users/86159/PycharmProjects/SQLanalysis; python -m pytest tests/test_sandbox.py tests/test_sql_guard.py -q
```
Expected: FAIL，`No module named 'safety'`

- [ ] **Step 3: 搬移实现**

```bash
cd c:/Users/86159/PycharmProjects/SQLanalysis; New-Item -ItemType Directory safety | Out-Null; New-Item safety/__init__.py -ItemType File | Out-Null; git mv utils/sandbox.py safety/sandbox.py; git mv tools/sql_tool.py safety/sql_guard.py
```
`safety/sandbox.py` 中 `from utils.config import MAX_RESULT_ROWS` → `from core.config import MAX_RESULT_ROWS`

- [ ] **Step 4: 运行确认通过**

```bash
cd c:/Users/86159/PycharmProjects/SQLanalysis; python -m pytest tests/test_sandbox.py tests/test_sql_guard.py -q
```
Expected: 10 passed

- [ ] **Step 5: 更新引用并提交**

`executors/base.py` → `from safety.sandbox import clean_code, run_generated_code`
`executors/sql_executor.py` → `from safety.sandbox import normalize_result`、`from safety.sql_guard import clean_sql, is_safe_sql, run_sql`

```bash
cd c:/Users/86159/PycharmProjects/SQLanalysis; python -m compileall -q .; python -m pytest tests -q; git add -A; git commit -m "refactor: promote sandbox and sql guard to safety package"
```

---

### Task 5: 建立 `llm/` 包

**Files:** Create `llm/{__init__,client,json_parse}.py`；Test `tests/test_json_parse.py`；Delete `utils/llm.py`、`utils/safe_json.py`、`utils/`

**Interfaces:**
- Produces: `llm.client.{get_llm,invoke_text,invoke_json}`、`llm.json_parse.extract_json_object(text) -> dict`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_json_parse.py
import pytest

from llm.json_parse import extract_json_object


def test_plain_json():
    assert extract_json_object('{"goal": "x"}') == {"goal": "x"}


def test_fenced_json_block():
    assert extract_json_object('```json\n{"goal": "x"}\n```') == {"goal": "x"}


def test_json_with_surrounding_text():
    assert extract_json_object('说明：\n{"goal": "x"}\n以上') == {"goal": "x"}


def test_trailing_comma_is_repaired():
    assert extract_json_object('{"a": 1, "b": 2,}') == {"a": 1, "b": 2}


def test_non_dict_is_rejected():
    with pytest.raises(ValueError):
        extract_json_object('[1, 2, 3]')


def test_garbage_is_rejected():
    with pytest.raises(ValueError):
        extract_json_object('完全没有 JSON')
```

- [ ] **Step 2: 运行确认失败**

```bash
cd c:/Users/86159/PycharmProjects/SQLanalysis; python -m pytest tests/test_json_parse.py -q
```
Expected: FAIL，`No module named 'llm'`

- [ ] **Step 3: 搬移实现**

```bash
cd c:/Users/86159/PycharmProjects/SQLanalysis; New-Item -ItemType Directory llm | Out-Null; New-Item llm/__init__.py -ItemType File | Out-Null; git mv utils/llm.py llm/client.py; git mv utils/safe_json.py llm/json_parse.py
```
`llm/client.py` 中 `from utils.safe_json import extract_json_object` → `from llm.json_parse import extract_json_object`

- [ ] **Step 4: 运行确认通过**

```bash
cd c:/Users/86159/PycharmProjects/SQLanalysis; python -m pytest tests/test_json_parse.py -q
```
Expected: 6 passed

- [ ] **Step 5: 更新引用并提交**

`agent/nodes.py`、`executors/base.py`、`executors/sql_executor.py`：`from utils.llm import ...` → `from llm.client import ...`

```bash
cd c:/Users/86159/PycharmProjects/SQLanalysis; Remove-Item -Recurse utils -ErrorAction SilentlyContinue; python -m compileall -q .; python -m pytest tests -q; git add -A; git commit -m "refactor: extract llm client and json parsing into llm package"
```

---

### Task 6: `tools/` 拆为 `analysis/` 与 `viz/`

**Files:** Create `analysis/{__init__,summarize,report,memory}.py`、`viz/{__init__,chart}.py`；Test `tests/test_columns.py`、`tests/test_report.py`；Delete `tools/`

**Interfaces:**
- Consumes: `core.columns`、`core.sanitize`
- Produces: `analysis.summarize.summarize_result(df)`、`analysis.report.build_report(question, plan, df) -> (list[str], str)`、`analysis.memory.extract_memory_from_result(question, plan, df) -> dict`、`viz.chart.{build_chart_spec,build_chart_figure}`

**拆分规则：** `tools/report_tool.py` 一分为三（函数体原样迁移）：`summarize_result` → `analysis/summarize.py`；`build_report` + `_fmt_value` → `analysis/report.py`；`extract_memory_from_result` → `analysis/memory.py`。`tools/chart_tool.py` 整体 → `viz/chart.py`。

- [ ] **Step 1: 写失败测试**

```python
# tests/test_columns.py
import pandas as pd

from core.columns import is_stable_focus_dimension, pick_dimension_column, pick_metric_column


def _df():
    return pd.DataFrame({
        "region": ["华东", "华南"],
        "month": ["2025-01", "2025-02"],
        "sales_amount": [10, 20],
        "order_id": [1, 2],
    })


def test_dimension_prefers_plan_value():
    assert pick_dimension_column(_df(), {"dimensions": ["month"]}) == "month"


def test_dimension_falls_back_to_non_numeric():
    assert pick_dimension_column(_df(), {}) == "region"


def test_metric_prefers_business_metric():
    assert pick_metric_column(_df(), {}) == "sales_amount"


def test_metric_ignores_id_columns():
    assert pick_metric_column(pd.DataFrame({"order_id": [1, 2], "qty": [3, 4]}), {}) == "qty"


def test_stable_dimension_detection():
    assert is_stable_focus_dimension("region")
    assert not is_stable_focus_dimension("channel")
    assert not is_stable_focus_dimension("month")
    assert not is_stable_focus_dimension(None)
```

```python
# tests/test_report.py
import pandas as pd

from analysis.memory import extract_memory_from_result
from analysis.report import build_report


def _df():
    return pd.DataFrame({"region": ["华东", "华南"], "sales_amount": [10.0, 30.0]})


def test_report_on_empty_result_mentions_empty():
    insights, report = build_report("q", {}, pd.DataFrame())
    assert insights and "空" in report


def test_report_names_top_dimension():
    insights, report = build_report("q", {"dimensions": ["region"]}, _df())
    assert "华南" in report and len(insights) >= 3


def test_memory_extracts_focus_entity():
    memory = extract_memory_from_result("q", {"dimensions": ["region"]}, _df())
    assert memory["focus_entities"]["region"] == "华南"
    assert memory["last_result"]["metric"] == "sales_amount"


def test_memory_on_empty_result_is_blank_but_valid():
    memory = extract_memory_from_result("q", {}, pd.DataFrame())
    assert memory["focus_entities"] == {}
    assert memory["last_result"]["question"] == "q"
```

- [ ] **Step 2: 运行确认失败**

```bash
cd c:/Users/86159/PycharmProjects/SQLanalysis; python -m pytest tests/test_columns.py tests/test_report.py -q
```
Expected: FAIL，`No module named 'analysis'`

- [ ] **Step 3: 拆包搬移**

```bash
cd c:/Users/86159/PycharmProjects/SQLanalysis; New-Item -ItemType Directory analysis,viz | Out-Null; New-Item analysis/__init__.py,viz/__init__.py -ItemType File | Out-Null; git mv tools/chart_tool.py viz/chart.py
```
按拆分规则切分 `tools/report_tool.py`，各文件 import：

```python
# analysis/summarize.py
from core.sanitize import make_json_safe

# analysis/report.py
from core.columns import pick_dimension_column, pick_metric_column

# analysis/memory.py
from core.columns import is_stable_focus_dimension, pick_dimension_column, pick_metric_column
from core.sanitize import make_json_safe
```

- [ ] **Step 4: 运行确认通过**

```bash
cd c:/Users/86159/PycharmProjects/SQLanalysis; python -m pytest tests/test_columns.py tests/test_report.py -q
```
Expected: 9 passed

- [ ] **Step 5: 更新引用并提交**

`agent/nodes.py` → `from viz.chart import build_chart_spec`、`from analysis.report import build_report`、`from analysis.memory import extract_memory_from_result`
`executors/base.py`、`executors/sql_executor.py` → `from analysis.summarize import summarize_result`
`app.py` → `from viz.chart import build_chart_figure`

```bash
cd c:/Users/86159/PycharmProjects/SQLanalysis; Remove-Item -Recurse tools -ErrorAction SilentlyContinue; python -m compileall -q .; python -m pytest tests -q; git add -A; git commit -m "refactor: split tools into analysis and viz packages"
```

---

### Task 7: Plan 校验层

**Files:** Create `agent/support/{__init__,plan_schema}.py`；Test `tests/test_plan_schema.py`；Modify `agent/nodes.py:plan_analysis_node`

**Interfaces:** Produces `agent.support.plan_schema.coerce_plan(raw: Any) -> AnalysisPlan`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_plan_schema.py
from agent.support.plan_schema import coerce_plan


def test_keeps_valid_plan():
    plan = coerce_plan({
        "goal": "各地区销售额", "metrics": ["sales_amount"], "dimensions": ["region"],
        "filters": {"region": "华南"}, "tool": "pandas",
        "needs_chart": True, "chart_type": "bar", "reason": "r",
    })
    assert plan["tool"] == "pandas" and plan["chart_type"] == "bar"
    assert plan["metrics"] == ["sales_amount"]


def test_invalid_chart_type_becomes_none():
    assert coerce_plan({"chart_type": "radar"})["chart_type"] == "none"


def test_invalid_tool_is_dropped():
    assert coerce_plan({"tool": "spark"})["tool"] is None


def test_dirty_collections_are_cleaned():
    plan = coerce_plan({"metrics": ["a", 1, None], "dimensions": "region", "filters": []})
    assert plan["metrics"] == ["a"]
    assert plan["dimensions"] == []
    assert plan["filters"] == {}


def test_non_dict_input_yields_empty_plan():
    plan = coerce_plan(["not", "a", "dict"])
    assert plan["goal"] == "" and plan["needs_chart"] is False
```

- [ ] **Step 2: 运行确认失败**

```bash
cd c:/Users/86159/PycharmProjects/SQLanalysis; python -m pytest tests/test_plan_schema.py -q
```
Expected: FAIL，`No module named 'agent.support'`

- [ ] **Step 3: 实现**

```python
# agent/support/plan_schema.py
from typing import Any, List

from agent.state import AnalysisPlan

ALLOWED_CHART_TYPES = {"line", "bar", "pie", "hist", "none"}
ALLOWED_TOOLS = {"pandas", "sql", "dask"}


def _as_str(value: Any) -> str:
    return value if isinstance(value, str) else ""


def _as_str_list(value: Any) -> List[str]:
    if isinstance(value, str):
        return [value]
    if not isinstance(value, (list, tuple)):
        return []
    return [v for v in value if isinstance(v, str) and v.strip()]


def coerce_plan(raw: Any) -> AnalysisPlan:
    if not isinstance(raw, dict):
        raw = {}

    tool = raw.get("tool")
    chart_type = raw.get("chart_type")

    return AnalysisPlan(
        goal=_as_str(raw.get("goal")),
        metrics=_as_str_list(raw.get("metrics")),
        dimensions=_as_str_list(raw.get("dimensions")),
        filters=raw.get("filters") if isinstance(raw.get("filters"), dict) else {},
        time_range=_as_str(raw.get("time_range")),
        tool=tool if tool in ALLOWED_TOOLS else None,
        needs_chart=bool(raw.get("needs_chart", False)),
        chart_type=chart_type if chart_type in ALLOWED_CHART_TYPES else "none",
        reason=_as_str(raw.get("reason")),
    )
```

- [ ] **Step 4: 运行确认通过**

```bash
cd c:/Users/86159/PycharmProjects/SQLanalysis; python -m pytest tests/test_plan_schema.py -q
```
Expected: 5 passed

- [ ] **Step 5: 接入 plan 节点**

`agent/nodes.py` 顶部增加 `from agent.support.plan_schema import coerce_plan`，`plan_analysis_node` 内改为：

```python
        plan = invoke_json(PLANNER_SYSTEM_PROMPT, json.dumps(payload, ensure_ascii=False))
        plan = coerce_plan(plan)
```

- [ ] **Step 6: 提交**

```bash
cd c:/Users/86159/PycharmProjects/SQLanalysis; python -m pytest tests -q; git add -A; git commit -m "feat: validate LLM analysis plan before use"
```

---

### Task 8: 状态分组 + reducer（核心）

**Files:** Modify `agent/state.py`（全量重写）、`agent/nodes.py`、`agent/graph.py`；Delete `agent/schemas.py`；Test `tests/test_state_groups.py`

**Interfaces:** 后续所有任务一律使用分组路径（见映射表）。

**字段映射（旧 → 新）：**

| 旧字段 | 新路径 |
|---|---|
| `thread_id / user_question / followup_mode / file_path / data_source_type` | `input.*` |
| `dataset_profile / schema_info / sample_rows` | `dataset.*` |
| `analysis_plan / selected_tool / needs_chart` | `plan.*` |
| `generated_artifact / generated_sql / generated_pandas_code / generated_dask_code` | `artifact.code`（种类 `artifact.kind`） |
| `approval_required / approved / approval_payload` | `artifact.*` |
| `execution_result_rows / execution_result_summary / retry_count / max_retries` | `execution.*` |
| `chart_spec / chart_ready / final_insights / final_report` | `output.*` |
| `run_logs / trace / memory / prior_questions / error / last_error_stage / terminal` | `run.*` |

- [ ] **Step 1: 写失败测试**

```python
# tests/test_state_groups.py
from agent.state import AgentState, merge_group, merge_run


def test_merge_group_keeps_untouched_keys():
    assert merge_group({"a": 1}, {"b": 2}) == {"a": 1, "b": 2}


def test_merge_run_clears_error_when_not_set():
    assert merge_run({"error": "old"}, {"logs": ["x"]}) == {"error": "", "logs": ["x"]}


def test_merge_run_keeps_explicit_error():
    assert merge_run({"error": "old"}, {"error": "new"}) == {"error": "new"}


def test_agent_state_groups_exist():
    for key in ("input", "dataset", "plan", "artifact", "execution", "output", "run"):
        assert key in AgentState.__annotations__
```

- [ ] **Step 2: 运行确认失败**

```bash
cd c:/Users/86159/PycharmProjects/SQLanalysis; python -m pytest tests/test_state_groups.py -q
```
Expected: FAIL（`merge_group` 未定义）

- [ ] **Step 3: 重写 `agent/state.py`**

```python
from typing import Annotated, Any, Dict, List, Literal, TypedDict


def merge_group(old: Dict[str, Any] | None, new: Dict[str, Any] | None) -> Dict[str, Any]:
    return {**(old or {}), **(new or {})}


def merge_run(old: Dict[str, Any] | None, new: Dict[str, Any] | None) -> Dict[str, Any]:
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
```

- [ ] **Step 4: 运行确认通过**

```bash
cd c:/Users/86159/PycharmProjects/SQLanalysis; python -m pytest tests/test_state_groups.py -q
```
Expected: 4 passed

- [ ] **Step 5: 改写节点（按映射表逐节点替换字段路径）**

两个代表性节点（`agent/nodes.py`）：

```python
def load_data_node(state: AgentState) -> AgentState:
    try:
        data_input = state.get("input", {})
        file_path = data_input.get("file_path")
        data_source_type = data_input.get("data_source_type")

        if not file_path:
            return {
                "run": {
                    "error": "Missing file_path in state.",
                    "run_logs": append_log(state, "Load data failed: missing file_path."),
                    "trace": append_trace(state, "load_data", "error", {"reason": "missing file_path"}),
                    "last_error_stage": "load_data",
                }
            }
        # csv / excel / sqlite 三个分支同理，返回 {"dataset": {...}, "run": {...}}
```

```python
def execute_artifact_node(state: AgentState) -> AgentState:
    try:
        executor = get_executor(state["plan"]["selected_tool"])
        result = executor.execute(state)

        if result.get("error"):
            return {
                "run": {
                    "error": result["error"],
                    "terminal": bool(result.get("terminal", False)),
                    "run_logs": append_log(state, f"Execute artifact failed by executor={executor.name}."),
                    "trace": append_trace(state, "execute_artifact", "error",
                                          {"executor": executor.name, "reason": result.get("error", "")}),
                    "last_error_stage": "execute_artifact",
                }
            }

        return {
            "execution": {"rows": result["rows"], "summary": result.get("summary", {})},
            "run": {
                "run_logs": append_log(state, f"Executed artifact by executor={executor.name}."),
                "trace": append_trace(state, "execute_artifact", "ok",
                                      {"executor": executor.name, "rows": len(result.get("rows", []))}),
            },
        }
    except Exception as e:
        return {
            "run": {
                "error": f"Execute artifact failed: {e}",
                "terminal": False,
                "run_logs": append_log(state, f"Execute artifact failed: {e}"),
                "trace": append_trace(state, "execute_artifact", "error", {"reason": str(e)}),
                "last_error_stage": "execute_artifact",
            }
        }
```

`generate_artifact_node` / `repair_artifact_node` 的产物字段改为：

```python
        return {
            "artifact": {
                "kind": state["plan"]["selected_tool"],
                "code": code,
                "approval_required": need_approval,
                "approval_payload": executor.get_approval_payload(merged_state) if need_approval else {},
            },
            "run": {...},
        }
```

`agent/graph.py` 的条件边谓词同步改读分组：`state.get("run", {}).get("error")`、`state.get("artifact", {}).get("approval_required")`、`state.get("execution", {}).get("retry_count", 0)`、`state.get("plan", {}).get("selected_tool")`。

- [ ] **Step 6: 同步 executor 返回结构**

`executors/base.py` 与 `executors/sql_executor.py` 的 `execute()`：

```python
        return make_json_safe({
            "rows": result_df.to_dict(orient="records"),
            "summary": summarize_result(result_df),
            "error": "",
            "terminal": False,
        })
```
`executors/base.py` 的 `generate/repair`：`{"code": code, "error": "", "retry_count": ...}`。`executors/sql_executor.py` 的 `generate/repair` 同样只返回 `code`（SQL 文本）+ `error`/`terminal`；`get_approval_payload` 返回体中的 `sql` 键保留（供 UI 判定语言）。

- [ ] **Step 7: 删除 `agent/schemas.py` 并提交**

```bash
cd c:/Users/86159/PycharmProjects/SQLanalysis; git rm agent/schemas.py; python -m compileall -q .; python -m pytest tests -q; git add -A; git commit -m "refactor: group AgentState into sub-states with reducers"
```

注：本任务会让 `app.py` / `eval_runner.py` 暂时读不到旧字段，Task 9 立即修复；中途只以 `pytest tests -q` 验证。

---

### Task 9: Service 门面 + DTO（UI 解耦）

**Files:** Create `service.py`；Test `tests/test_service.py`；Modify `app.py`、`eval_runner.py`

**Interfaces:**
- Consumes: 分组后的 `AgentState`、`agent.graph.build_graph(executors=None)`（Task 11 增加该参数；本任务可先按现状调用 `build_graph()`）
- Produces: `AnalysisService.start_analysis(file_path, source_type, question, followup=False, memory=None) -> RunResult`、`AnalysisService.resume(thread_id, approved) -> RunResult`；`RunResult.status ∈ {"completed", "awaiting_approval", "failed"}`

- [ ] **Step 1: 写失败测试（FakeLLM + FakeExecutor，不联网）**

```python
# tests/test_service.py
import pandas as pd
import pytest

import agent.nodes as nodes
import executors
from executors.base import BaseExecutor
from service import AnalysisService


class FakeExecutor(BaseExecutor):
    name = "pandas"

    def __init__(self, fail=False, terminal=False):
        self.fail = fail
        self.terminal = terminal

    def supports(self, state):
        return True

    def generate(self, state):
        return {"code": "result_df = df.head(2)", "error": ""}

    def repair(self, state):
        return {"code": "result_df = df.head(1)", "error": "", "retry_count": 1}

    def needs_approval(self, state):
        return True

    def get_approval_payload(self, state):
        return {"kind": "pandas", "title": "t", "content": "result_df = df.head(2)", "message": "ok?"}

    def execute(self, state):
        if self.fail:
            return {"rows": [], "summary": {}, "error": "SQL execution not approved.", "terminal": self.terminal}
        df = pd.DataFrame({"region": ["华东"], "sales_amount": [1.0]})
        return {"rows": df.to_dict(orient="records"), "summary": {}, "error": "", "terminal": False}


PLAN = {"goal": "g", "metrics": ["sales_amount"], "dimensions": ["region"], "filters": {},
        "time_range": "", "tool": "pandas", "needs_chart": True, "chart_type": "bar", "reason": ""}


@pytest.fixture(autouse=True)
def fake_llm(monkeypatch):
    monkeypatch.setattr(nodes, "invoke_json", lambda *a, **k: dict(PLAN))
    monkeypatch.setattr(nodes, "invoke_text", lambda *a, **k: "result_df = df.head(2)")


@pytest.fixture(autouse=True)
def fake_executors():
    executors.init_executors()
    yield
    executors.registry._EXECUTOR_REGISTRY.clear()


def _service(fail=False, terminal=False):
    # 顺序要紧：先建 service（内部会 init_executors 注册真实执行器），
    # 再用同名 FakeExecutor 覆盖 "pandas"
    svc = AnalysisService()
    executors.register_executor(FakeExecutor(fail=fail, terminal=terminal))
    return svc


def test_start_returns_awaiting_approval():
    result = _service().start_analysis("dummy.csv", "csv", "问题")
    assert result.status == "awaiting_approval"
    assert result.pending is not None and result.pending.kind == "pandas"
    assert result.pending.language == "python"


def test_approve_runs_to_completion():
    svc = _service()
    first = svc.start_analysis("dummy.csv", "csv", "问题")
    second = svc.resume(first.thread_id, approved=True)
    assert second.status == "completed"
    assert second.rows and second.report


def test_reject_terminates_without_new_approval():
    svc = _service(fail=True, terminal=True)
    first = svc.start_analysis("dummy.csv", "csv", "问题")
    assert first.status == "awaiting_approval"
    second = svc.resume(first.thread_id, approved=False)
    assert second.status == "failed"
    assert second.pending is None
    assert "not approved" in second.error.lower()


def test_each_start_uses_fresh_thread():
    svc = _service()
    a = svc.start_analysis("dummy.csv", "csv", "问题1")
    b = svc.start_analysis("dummy.csv", "csv", "问题2")
    assert a.thread_id != b.thread_id
```

- [ ] **Step 2: 运行确认失败**

```bash
cd c:/Users/86159/PycharmProjects/SQLanalysis; python -m pytest tests/test_service.py -q
```
Expected: FAIL，`No module named 'service'`

- [ ] **Step 3: 实现 `service.py`**

```python
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
import uuid

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
    status: str
    tool: str = ""
    plan: Dict[str, Any] = field(default_factory=dict)
    pending: Optional[PendingApproval] = None
    artifact_kind: str = ""
    artifact_code: str = ""
    rows: List[Dict[str, Any]] = field(default_factory=list)
    chart_spec: Dict[str, Any] = field(default_factory=dict)
    chart_ready: bool = False
    insights: List[str] = field(default_factory=list)
    report: str = ""
    trace: List[Dict[str, Any]] = field(default_factory=list)
    logs: List[str] = field(default_factory=list)
    memory: Dict[str, Any] = field(default_factory=dict)
    error: str = ""


def _empty_groups() -> Dict[str, Any]:
    return {
        "artifact": {"kind": "", "code": "", "approval_required": False, "approved": False, "approval_payload": {}},
        "execution": {"rows": [], "summary": {}, "retry_count": 0, "max_retries": DEFAULT_MAX_RETRIES},
        "output": {"chart_spec": {}, "chart_ready": False, "insights": [], "report": ""},
        "run": {"error": "", "terminal": False, "last_error_stage": ""},
    }


def _to_result(thread_id: str, state: Dict[str, Any], raw: Dict[str, Any]) -> RunResult:
    plan = state.get("plan", {})
    artifact = state.get("artifact", {})
    execution = state.get("execution", {})
    output = state.get("output", {})
    run = state.get("run", {})

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

    def _config(self, thread_id: str) -> dict:
        return {"configurable": {"thread_id": thread_id}}

    def start_analysis(self, file_path: str, source_type: str, question: str,
                       followup: bool = False, memory: Optional[dict] = None) -> RunResult:
        thread_id = str(uuid.uuid4())
        state: Dict[str, Any] = {
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

        raw = self._graph.invoke(state, config=self._config(thread_id))
        return _to_result(thread_id, self._graph.get_state(self._config(thread_id)).values, raw)

    def resume(self, thread_id: str, approved: bool) -> RunResult:
        raw = self._graph.invoke(Command(resume=approved), config=self._config(thread_id))
        return _to_result(thread_id, self._graph.get_state(self._config(thread_id)).values, raw)
```

- [ ] **Step 4: 运行确认通过**

```bash
cd c:/Users/86159/PycharmProjects/SQLanalysis; python -m pytest tests/test_service.py -q
```
Expected: 4 passed

- [ ] **Step 5: 改写 `app.py`**

`app.py` 只保留 UI：删除 `fresh_run_state()` 与 `handle_result()` 中的 `__interrupt__` 解析（移入 service），改为：

```python
from service import AnalysisService


@st.cache_resource
def get_service() -> AnalysisService:
    return AnalysisService()


service = get_service()

if start_btn:
    st.session_state.result = service.start_analysis(
        st.session_state.file_path, st.session_state.data_source_type, question
    )

if followup_btn:
    previous = st.session_state.result
    st.session_state.result = service.start_analysis(
        st.session_state.file_path, st.session_state.data_source_type, question,
        followup=True, memory=previous.memory if previous else None,
    )

if st.button("批准执行"):
    st.session_state.result = service.resume(st.session_state.result.thread_id, True)

if st.button("拒绝执行"):
    st.session_state.result = service.resume(st.session_state.result.thread_id, False)

result = st.session_state.result
if result and result.pending:
    st.subheader("执行审批")
    st.code(result.pending.content, language=result.pending.language)
```
结果展示区改用 `result.rows / result.chart_spec / result.chart_ready / result.insights / result.report / result.trace`；`thread_id` 从 `result.thread_id` 读取，不再自行生成。

- [ ] **Step 6: 改写 `eval_runner.py`**

删除 `build_init_state` 与 `invoke_until_done`，改为调用 service 并自动批准：

```python
from service import AnalysisService


def run_turn(service: AnalysisService, file_path: str, source_type: str, question: str,
             followup: bool = False, memory: dict | None = None):
    result = service.start_analysis(file_path, source_type, question, followup=followup, memory=memory)
    for _ in range(3):
        if result.pending is None:
            break
        result = service.resume(result.thread_id, True)
    return result
```
`summarize_result(case, result)` 改为读 `result.tool / result.chart_ready / result.report / result.insights / result.rows / result.error`。

- [ ] **Step 7: 提交**

```bash
cd c:/Users/86159/PycharmProjects/SQLanalysis; python -m compileall -q .; python -m pytest tests -q; git add -A; git commit -m "refactor: add service facade and decouple UI from agent state"
```

---

### Task 10: 拆 `agent/nodes/` 包 + `routing.py`

**Files:** Create `agent/nodes/{__init__,load,plan,artifact,approval,chart,report,failure}.py`、`agent/routing.py`；Modify `agent/graph.py`；Delete `agent/nodes.py`

**Interfaces:** `agent/nodes/__init__.py` 导出全部节点函数；`agent/routing.py` 导出 `after_plan / after_generate_artifact / after_approval / after_execute_artifact / after_repair_artifact / after_build_chart`

- [ ] **Step 1: 拆分**

按函数原样迁移（不改写逻辑）：
- `load.py`：`load_data_node`
- `plan.py`：`plan_analysis_node`
- `artifact.py`：`generate_artifact_node` / `repair_artifact_node` / `execute_artifact_node`
- `approval.py`：`approval_node`
- `chart.py`：`build_chart_node`
- `report.py`：`report_node`
- `failure.py`：`error_node`
- 辅助函数 `append_log` / `append_trace` 放入 `agent/support/tracing.py`（Task 7 已建 `agent/support/`）

`agent/nodes/__init__.py`：

```python
from agent.nodes.load import load_data_node
from agent.nodes.plan import plan_analysis_node
from agent.nodes.artifact import (
    generate_artifact_node,
    repair_artifact_node,
    execute_artifact_node,
)
from agent.nodes.approval import approval_node
from agent.nodes.chart import build_chart_node
from agent.nodes.report import report_node
from agent.nodes.failure import error_node

__all__ = [
    "load_data_node", "plan_analysis_node", "generate_artifact_node",
    "repair_artifact_node", "execute_artifact_node", "approval_node",
    "build_chart_node", "report_node", "error_node",
]
```

- [ ] **Step 2: 拆出 `agent/routing.py`**

把 `agent/graph.py` 里的 `after_*` 六个谓词原样移到 `agent/routing.py`，`agent/graph.py` 改为 `from agent.routing import (...)`，并在 `build_graph` 里接受可选执行器列表：

```python
def build_graph(executors_list=None):
    if executors_list is None:
        init_executors()
    else:
        for executor in executors_list:
            register_executor(executor)
    ...
```

- [ ] **Step 3: 验证并提交**

```bash
cd c:/Users/86159/PycharmProjects/SQLanalysis; python -m compileall -q .; python -m pytest tests -q; git add -A; git commit -m "refactor: split nodes into package and extract routing predicates"
```

---

### Task 11: prompt 注入 executors（解环）

**Files:** Modify `executors/base.py`、`executors/pandas_executor.py`、`executors/dask_executor.py`、`executors/sql_executor.py`、`executors/__init__.py`；Test `tests/test_executor_registry.py`

**Interfaces:** `CodeExecutor.__init__(generator_prompt, repair_prompt, artifact_kind)`；`executors` 不再 import `agent.prompts`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_executor_registry.py
import sys

import executors
from executors.base import BaseExecutor
from executors.registry import get_executor, list_executors


def test_executors_do_not_import_agent():
    assert "agent.prompts" not in sys.modules or True  # 见 Step 3 说明


def test_custom_executor_can_be_registered():
    class Dummy(BaseExecutor):
        name = "dummy"

        def supports(self, state):
            return True

        def generate(self, state):
            return {"code": "", "error": ""}

        def execute(self, state):
            return {"rows": [], "summary": {}, "error": "", "terminal": False}

    executors.register_executor(Dummy())
    assert "dummy" in list_executors()
    assert get_executor("dummy").name == "dummy"


def test_prompts_are_injected_not_imported():
    executor = get_executor("pandas")
    assert executor.generator_prompt and executor.repair_prompt
    assert executor.artifact_kind == "pandas"
```

- [ ] **Step 2: 运行确认失败**

```bash
cd c:/Users/86159/PycharmProjects/SQLanalysis; python -m pytest tests/test_executor_registry.py -q
```
Expected: FAIL（`generator_prompt` 当前是类属性常量，非注入）

- [ ] **Step 3: 改造**

`executors/base.py`：

```python
class CodeExecutor(BaseExecutor):
    def __init__(self, generator_prompt: str, repair_prompt: str, artifact_kind: str):
        self.generator_prompt = generator_prompt
        self.repair_prompt = repair_prompt
        self.artifact_kind = artifact_kind
```
类属性 `generator_prompt / repair_prompt / artifact_key` 删除，改为实例属性；`artifact_key` 一律用 `self.artifact_kind`。

`executors/pandas_executor.py` / `dask_executor.py` 删除 `from agent.prompts import ...`。

`executors/__init__.py`：

```python
def init_executors() -> None:
    from agent.prompts import (
        PANDAS_GENERATOR_PROMPT, PANDAS_REPAIR_PROMPT,
        SQL_GENERATOR_PROMPT, SQL_REPAIR_PROMPT,
        DASK_GENERATOR_PROMPT, DASK_REPAIR_PROMPT,
    )

    register_executor(SQLExecutor(generator_prompt=SQL_GENERATOR_PROMPT,
                                  repair_prompt=SQL_REPAIR_PROMPT,
                                  artifact_kind="sql"))
    register_executor(PandasExecutor(generator_prompt=PANDAS_GENERATOR_PROMPT,
                                     repair_prompt=PANDAS_REPAIR_PROMPT,
                                     artifact_kind="pandas"))
    try:
        from executors.dask_executor import DaskExecutor
        register_executor(DaskExecutor(generator_prompt=DASK_GENERATOR_PROMPT,
                                       repair_prompt=DASK_REPAIR_PROMPT,
                                       artifact_kind="dask"))
    except ImportError as e:
        logger.warning("Dask executor disabled: %s", e)
```

测试里 `test_executors_do_not_import_agent` 的断言改为实质检查（Step 3 完成后替换）：

```python
def test_executors_do_not_import_agent():
    import subprocess, sys
    code = "import executors; assert 'agent.prompts' not in __import__('sys').modules"
    assert subprocess.call([sys.executable, "-c", code]) == 0
```

- [ ] **Step 4: 运行确认通过**

```bash
cd c:/Users/86159/PycharmProjects/SQLanalysis; python -m pytest tests -q
```
Expected: 全部通过（含新增 3 条）

- [ ] **Step 5: 提交**

```bash
git add -A; git commit -m "refactor: inject prompts into executors to break agent dependency"
```

---

### Task 12: 收尾与验收

**Files:** Modify `README.md`（若无则创建）；全库复核

- [ ] **Step 1: 清理残留**

```bash
cd c:/Users/86159/PycharmProjects/SQLanalysis; Get-ChildItem -Recurse -Include *.pyc,__pycache__ | Remove-Item -Recurse -Force; git status --short
```
确认：无 `tools/`、`utils/`、`agent/schemas.py`、`agent/nodes.py`（已拆包）、`generated_*` 字段残留：

```bash
cd c:/Users/86159/PycharmProjects/SQLanalysis; Select-String -Path *.py,agent\*.py,executors\*.py,core\*.py,safety\*.py,llm\*.py,analysis\*.py,viz\*.py -Pattern "generated_sql|generated_pandas_code|generated_dask_code|from utils|from tools" | Measure-Object
```
Expected: Count = 0

- [ ] **Step 2: 全量验证**

```bash
cd c:/Users/86159/PycharmProjects/SQLanalysis; python -m compileall -q .; python -m pytest tests -q
```
Expected: 全部通过；`python -c "import app; print('ok')"` 仅输出 streamlit bare mode 警告后打印 `ok`

- [ ] **Step 3: 写 `README.md` 结构说明**

内容包含：包职责表（`core/safety/llm/analysis/viz/executors/agent/service`）、新增数据源与新增执行引擎的接入步骤、运行命令（`streamlit run app.py`、`python eval_runner.py`、`pytest tests`）。

- [ ] **Step 4: 提交**

```bash
git add -A; git commit -m "docs: document refactored package structure"
```

- [ ] **Step 5: 人工验收清单（需 API key，由用户执行）**

1. `streamlit run app.py` 上传 CSV → 分析 → 审批 → 执行 → 图表 → 结论；
2. 拒绝审批后流程终止并提示，不再重新弹出审批；
3. `python eval_runner.py` 产出 `eval_single_turn_results.csv` / `eval_multi_turn_results.csv`，无 exception 行；
4. 上传 SQLite 走 SQL 路径，审批面板显示 SQL（语言高亮为 sql）。

---

## Self-Review 结论

- Spec 覆盖：3 节目标结构 → Task 3-6、10；4 节状态模型 → Task 2（POC）+ Task 8；5 节 Service/DTO → Task 9；6 节 Plan 校验 → Task 7；7 节 Executor 解耦 → Task 11；8 节迁移顺序 0/1/2/3/4/5/6/7 → Task 1/2/3-6/7/8/9/10/11；9 节测试 → 各任务内嵌 + Task 12；10 节风险 → Task 2 fallback + Task 12 人工验收；11 节既有修复 → Task 4（sandbox/sql_guard）、Task 9（拒绝终止 + 任意路径 interrupt）。
- 类型一致性：`RunResult`、`PendingApproval`、`coerce_plan`、`artifact.kind/code`、`execution.rows/summary` 在 Task 8/9/11 中命名一致；`AnalysisPlan` 由 `agent/state.py` 定义、被 `agent/support/plan_schema.py` 引用。
- 无 TBD/占位：所有步骤均给出具体命令或代码。

