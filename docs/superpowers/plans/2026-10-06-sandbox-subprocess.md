# Sandbox Subprocess Isolation — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把生成的 pandas/dask 代码从父进程内 `exec` 移到独立子进程中执行，父进程通过超时强制 kill 来控制隔离与资源，闭合安全模型。

**Architecture:** 新增子进程入口 `safety/code_runner.py`（由 `python -m safety.code_runner` 启动），通过临时文件接收请求、回传结果（`res_<uuid>.pkl`）或错误（`err_<uuid>.json`）+ 退出码。父进程侧在 `safety/sandbox.py` 新增 `run_generated_code_subprocess`，由 `executors/base.py::execute` 调用。`sandbox.py` 抽出 `_execute_code_impl` 内核，保留进程内 `run_generated_code` 供现有单测。

**Tech Stack:** Python 3.11、`subprocess`（标准库）、`pickle`/`json` 临时文件通信、`resource.setrlimit`（仅 Linux）、`pytest`。

## Global Constraints

- 隔离机制：独立子进程（`subprocess`），跨平台超时 kill。
- 覆盖范围：仅 Code 类执行器（pandas / dask）；SQL 执行器（sqlite）保持不变。
- 数据传入：子进程按 `file_path` 重新加载，父进程只传 code + file_path + source_type + executor_name。
- 限额：`CODE_EXEC_TIMEOUT=30.0`s 跨平台；`CODE_EXEC_MEM_LIMIT_MB=1024` 与 `CODE_EXEC_CPU_TIME=30` 仅 Linux `resource.setrlimit` 生效，Windows 无 `resource` 模块时自动退化为仅超时。
- 错误分类：静态校验失败（validate 抛 `ValueError`）→ `terminal=True`（不重试）；运行期错误 / 超时 / 内存超限 / 子进程崩溃 → `terminal=False`（进 `repair_artifact`）。
- `CodeExecutor.execute` 对外签名与返回结构（`rows / summary / error / terminal`）不变。
- **git 提交需用户明确授权，本计划默认不自动 `git commit`；每个任务末尾的 commit 步骤仅在用户同意时执行。**
- 所有子进程相关单测须在本机（Windows）跑通。

---

## File Structure

- **Modify `core/config.py`** — 新增 3 个超时/限额配置项。
- **Modify `safety/sandbox.py`** — 新增 `SandboxValidationError` / `SandboxExecError` 异常；抽出 `_execute_code_impl`；保留 `run_generated_code`；新增 `run_generated_code_subprocess`（父进程侧）。
- **Create `safety/code_runner.py`** — 子进程入口：资源限制、按 executor_name 加载数据、调用 `_execute_code_impl`、写结果/错误文件、退出码。
- **Modify `executors/base.py`** — `CodeExecutor.execute` 改为调用 `run_generated_code_subprocess`，父进程不再 `load_frame`，捕获两类异常映射 `terminal`。
- **Create `tests/test_code_runner.py`** — 端到端子进程测试 + 异常分类测试 + mock 超时/崩溃。
- **Modify `README.md`** — 环境变量表新增 3 项；安全模型与已知限制更新子进程说明。

---

### Task 1: 配置项 `core/config.py`

**Files:**
- Modify: `core/config.py:52`

**Interfaces:**
- Produces: `CODE_EXEC_TIMEOUT: float`、`CODE_EXEC_MEM_LIMIT_MB: int`、`CODE_EXEC_CPU_TIME: int`（供 `safety/code_runner.py` 与 `executors/base.py` 导入）。

- [ ] **Step 1: Write the failing test**

创建 `tests/test_config_subprocess.py`:
```python
from core.config import CODE_EXEC_TIMEOUT, CODE_EXEC_MEM_LIMIT_MB, CODE_EXEC_CPU_TIME


def test_subprocess_config_defaults():
    assert CODE_EXEC_TIMEOUT == 30.0
    assert CODE_EXEC_MEM_LIMIT_MB == 1024
    assert CODE_EXEC_CPU_TIME == 30
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_config_subprocess.py -v`
Expected: FAIL with `ImportError: cannot import name 'CODE_EXEC_TIMEOUT'`

- [ ] **Step 3: Write minimal implementation**

在 `core/config.py` 末尾（`LLM_RETRY_MAX_DELAY` 之后）追加：
```python
# 子进程执行生成的代码时，父进程等待的最大秒数（超时强制 kill）
CODE_EXEC_TIMEOUT = _get_float("CODE_EXEC_TIMEOUT", 30.0)

# 子进程虚拟内存上限（MB），仅 Linux 的 resource.setrlimit(RLIMIT_AS) 生效
CODE_EXEC_MEM_LIMIT_MB = _get_int("CODE_EXEC_MEM_LIMIT_MB", 1024)

# 子进程 CPU 时间上限（秒），仅 Linux 的 resource.setrlimit(RLIMIT_CPU) 生效
CODE_EXEC_CPU_TIME = _get_int("CODE_EXEC_CPU_TIME", 30)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_config_subprocess.py -v`
Expected: PASS

- [ ] **Step 5: Commit（需用户授权）**

```bash
git add core/config.py tests/test_config_subprocess.py
git commit -m "feat(config): add subprocess exec timeout and resource limits"
```

---

### Task 2: 重构 `safety/sandbox.py`（抽出内核 + 异常）

**Files:**
- Modify: `safety/sandbox.py`（`run_generated_code` 附近）
- Test: `tests/test_sandbox.py`（已有，保持不变）

**Interfaces:**
- Consumes: 现有 `clean_code`、`validate_code`、`build_safe_globals`、`normalize_result`。
- Produces: `_execute_code_impl(code, variables) -> pd.DataFrame`（供 `code_runner.py` 与 `run_generated_code` 调用）；`SandboxValidationError(ValueError)`、`SandboxExecError(RuntimeError)`（供 `run_generated_code_subprocess` 与 `executors/base.py` 使用）。

- [ ] **Step 1: Write the failing test**

在 `tests/test_sandbox.py` 顶部 import 后追加：
```python
from safety.sandbox import SandboxExecError, SandboxValidationError, _execute_code_impl


def test_impl_runtime_error_wrapped_as_exec_error():
    with pytest.raises(SandboxExecError):
        _execute_code_impl("result_df = df['missing_col']", {"df": _df(), "pd": pd})


def test_impl_validation_error_is_validation_type():
    # 注意：clean_code 会去掉 "import " 开头行，故用 __import__() 独立行触发校验
    with pytest.raises(SandboxValidationError):
        _execute_code_impl("result_df = df.head(1)\n__import__('os')", {"df": _df(), "pd": pd})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_sandbox.py -v`
Expected: FAIL with `ImportError` / `AttributeError`（`_execute_code_impl` / `SandboxExecError` 尚不存在）

- [ ] **Step 3: Write minimal implementation**

将 `safety/sandbox.py` 顶部的 `run_generated_code` 函数替换为以下内容（保留 `clean_code` / `validate_code` / `build_safe_globals` / `normalize_result` 不变）：
```python
class SandboxValidationError(ValueError):
    """静态校验失败（import / while / dunder / 禁调函数等）：终止性错误，不应重试。"""


class SandboxExecError(RuntimeError):
    """运行期执行错误 / 超时 / 子进程崩溃：可重试。"""


def _execute_code_impl(code: str, variables: Dict[str, Any] | None = None) -> pd.DataFrame:
    """清洗 -> 静态校验 -> 受限执行 -> 归一化（不含进程边界）。

    静态校验失败抛 SandboxValidationError（terminal）；
    运行期执行异常统一包成 SandboxExecError（可重试）。
    """
    code = clean_code(code)
    if not code:
        raise SandboxValidationError("生成代码为空。")
    try:
        validate_code(code)
    except ValueError as e:
        raise SandboxValidationError(str(e)) from e

    namespace = build_safe_globals(variables)
    namespace.setdefault("result_df", None)
    try:
        exec(code, namespace, namespace)
    except Exception as e:  # noqa: BLE001
        raise SandboxExecError(f"代码执行出错: {e}") from e

    return normalize_result(namespace.get("result_df"))


def run_generated_code(code: str, variables: Dict[str, Any] | None = None) -> pd.DataFrame:
    """进程内执行（保留供现有单测与遗留调用）。"""
    return _execute_code_impl(code, variables)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_sandbox.py -v`
Expected: PASS（原有 6 类恶意代码拦截、正常执行、未赋值等用例仍通过；新增 2 条用例通过）

- [ ] **Step 5: Commit（需用户授权）**

```bash
git add safety/sandbox.py tests/test_sandbox.py
git commit -m "refactor(sandbox): extract _execute_code_impl and add exec exceptions"
```

---

### Task 3: 子进程入口 `safety/code_runner.py`

**Files:**
- Create: `safety/code_runner.py`
- Test: `tests/test_code_runner.py`（本任务先建文件，测试在 Task 5 补全）

**Interfaces:**
- Consumes: `core.config.CODE_EXEC_MEM_LIMIT_MB` / `CODE_EXEC_CPU_TIME`、`safety.sandbox._execute_code_impl`、`executors.pandas_executor.load_dataframe_by_type`、`executors.dask_executor.load_dask_dataframe`。
- Produces: `run(req: dict, res_path: str, err_path: str) -> int`（退出码 0 成功 / 非 0 失败）；`__main__` 入口读 `argv[1..3]` 为 req/res/err 路径。

- [ ] **Step 1: Write the failing test**

创建 `tests/test_code_runner.py`（本任务只覆盖纯函数分支）：
```python
import os
import sys

import pytest

from safety import code_runner


def test_apply_resource_limits_noop_on_windows():
    # Windows 无 resource 模块；调用不应抛异常
    code_runner._apply_resource_limits()


def test_extra_vars_pandas_only():
    vars_ = code_runner._extra_vars("pandas")
    assert "pd" in vars_
    assert "dd" not in vars_


def test_extra_vars_dask_has_dd():
    vars_ = code_runner._extra_vars("dask")
    assert "dd" in vars_ and "pd" in vars_


def test_classify_validation_terminal():
    assert code_runner._classify(ValueError("生成代码不允许 import。")) is True


def test_classify_runtime_non_terminal():
    assert code_runner._classify(RuntimeError("代码执行出错: x")) is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_code_runner.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'safety.code_runner'`

- [ ] **Step 3: Write minimal implementation**

创建 `safety/code_runner.py`：
```python
"""子进程执行入口：python -m safety.code_runner <req_json> <res_pkl> <err_json>

读取请求临时文件，按 executor_name 加载数据，执行生成的代码，
把结果（pickle）或错误（JSON）写回临时文件，并以退出码表达成败。
"""

import json
import sys

from core.config import CODE_EXEC_MEM_LIMIT_MB, CODE_EXEC_CPU_TIME
from safety.sandbox import _execute_code_impl

try:
    import resource
except ImportError:  # Windows 无此模块
    resource = None


def _apply_resource_limits() -> None:
    if resource is None:
        return
    mb = CODE_EXEC_MEM_LIMIT_MB * 1024 * 1024
    try:
        resource.setrlimit(resource.RLIMIT_AS, (mb, mb))
        resource.setrlimit(resource.RLIMIT_CPU, (CODE_EXEC_CPU_TIME, CODE_EXEC_CPU_TIME))
    except (ValueError, OSError):
        pass


def _load_frame(executor_name: str, file_path: str, source_type: str):
    if executor_name == "pandas":
        from executors.pandas_executor import load_dataframe_by_type
        return load_dataframe_by_type(file_path, source_type)
    if executor_name == "dask":
        from executors.dask_executor import load_dask_dataframe
        return load_dask_dataframe(file_path, source_type)
    raise ValueError(f"Unknown executor_name: {executor_name}")


def _extra_vars(executor_name: str) -> dict:
    import pandas as pd
    if executor_name == "dask":
        import dask.dataframe as dd
        return {"dd": dd, "pd": pd}
    return {"pd": pd}


def _classify(exc: Exception) -> bool:
    """静态校验失败（ValueError）视为终止性；其余（含运行期 RuntimeError）可重试。"""
    return isinstance(exc, ValueError)


def run(req: dict, res_path: str, err_path: str) -> int:
    """执行请求，写结果/错误文件，返回退出码（0 成功 / 非 0 失败）。"""
    import pickle
    try:
        _apply_resource_limits()
        frame = _load_frame(req["executor_name"], req["file_path"], req["source_type"])
        variables = {"df": frame, "result_df": None}
        variables.update(_extra_vars(req["executor_name"]))
        result_df = _execute_code_impl(req["code"], variables)
        with open(res_path, "wb") as f:
            pickle.dump(result_df, f)
        return 0
    except Exception as exc:  # noqa: BLE001
        with open(err_path, "w", encoding="utf-8") as f:
            json.dump(
                {"error": str(exc), "terminal": _classify(exc)},
                f,
                ensure_ascii=False,
            )
        return 1


if __name__ == "__main__":
    req_path, res_path, err_path = sys.argv[1], sys.argv[2], sys.argv[3]
    with open(req_path, "r", encoding="utf-8") as f:
        req = json.load(f)
    sys.exit(run(req, res_path, err_path))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_code_runner.py -v`
Expected: PASS

- [ ] **Step 5: Commit（需用户授权）**

```bash
git add safety/code_runner.py tests/test_code_runner.py
git commit -m "feat(safety): add subprocess code runner entrypoint"
```

---

### Task 4: 父进程侧 `run_generated_code_subprocess`

**Files:**
- Modify: `safety/sandbox.py`（在 `run_generated_code` 之后追加）
- Test: `tests/test_code_runner.py`（追加 mock 测试）

**Interfaces:**
- Consumes: `core.config.CODE_EXEC_TIMEOUT`、`safety.code_runner`（子进程模块）、`SandboxValidationError` / `SandboxExecError`（本文件定义）。
- Produces: `run_generated_code_subprocess(code, file_path, source_type, executor_name, timeout) -> pd.DataFrame`；超时/校验失败/崩溃分别抛 `SandboxExecError` / `SandboxValidationError` / `SandboxExecError`。

- [ ] **Step 1: Write the failing test**

在 `tests/test_code_runner.py` 追加（用 monkeypatch 模拟子进程，不真起进程）：
```python
import subprocess

from safety.sandbox import run_generated_code_subprocess, SandboxExecError, SandboxValidationError


class _FakeProc:
    def __init__(self, returncode, err=None):
        self.returncode = returncode
        self.stderr = b""
        self._err = err

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_subprocess_validation_error_raises_validation(monkeypatch, tmp_path):
    err = tmp_path / "err.json"
    err.write_text('{"error": "生成代码不允许 import。", "terminal": true}', encoding="utf-8")

    def fake_run(*a, **k):
        return _FakeProc(returncode=1)

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr("safety.sandbox._read_err_path", lambda p: {"error": "生成代码不允许 import。", "terminal": True})
    with pytest.raises(SandboxValidationError):
        run_generated_code_subprocess("x", "f.csv", "csv", "pandas", timeout=5.0)


def test_subprocess_timeout_raises_exec_error(monkeypatch):
    def fake_run(*a, **k):
        raise subprocess.TimeoutExpired(cmd="x", timeout=5.0)

    monkeypatch.setattr(subprocess, "run", fake_run)
    with pytest.raises(SandboxExecError) as ei:
        run_generated_code_subprocess("x", "f.csv", "csv", "pandas", timeout=5.0)
    assert "超时" in str(ei.value)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_code_runner.py -v`
Expected: FAIL with `AttributeError: module 'safety.sandbox' has no attribute 'run_generated_code_subprocess'`

- [ ] **Step 3: Write minimal implementation**

在 `safety/sandbox.py` 末尾追加（import 区块保持精简，函数内局部 import 避免循环依赖）：
```python
def _read_err_path(err_path: str) -> Dict[str, Any]:
    import json
    try:
        with open(err_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"error": "子进程异常退出（无错误详情）", "terminal": False}


def run_generated_code_subprocess(
    code: str,
    file_path: str,
    source_type: str,
    executor_name: str,
    timeout: float,
) -> "pd.DataFrame":
    """在独立子进程中执行生成的代码，返回截断后的 DataFrame。

    成功 -> 返回 DataFrame；
    子进程校验失败 -> 抛 SandboxValidationError（terminal）；
    子进程运行期错误 / 超时 / 崩溃 -> 抛 SandboxExecError（可重试）。
    """
    import json
    import os
    import pickle
    import subprocess
    import sys
    import tempfile
    import uuid

    base = tempfile.gettempdir()
    token = uuid.uuid4().hex
    req_path = os.path.join(base, f"datapilot_req_{token}.json")
    res_path = os.path.join(base, f"datapilot_res_{token}.pkl")
    err_path = os.path.join(base, f"datapilot_err_{token}.json")

    req = {
        "code": code,
        "file_path": file_path,
        "source_type": source_type,
        "executor_name": executor_name,
    }
    with open(req_path, "w", encoding="utf-8") as f:
        json.dump(req, f, ensure_ascii=False)

    try:
        proc = subprocess.run(
            [sys.executable, "-m", "safety.code_runner", req_path, res_path, err_path],
            timeout=timeout,
            capture_output=True,
        )
    except subprocess.TimeoutExpired:
        raise SandboxExecError(f"执行超时（>{timeout}s），已强制终止。") from None
    finally:
        if os.path.exists(req_path):
            os.remove(req_path)

    if proc.returncode != 0:
        err = _read_err_path(err_path)
        terminal = bool(err.get("terminal", False))
        if terminal:
            raise SandboxValidationError(err.get("error", "代码校验失败。"))
        raise SandboxExecError(err.get("error", "子进程执行失败。"))

    try:
        with open(res_path, "rb") as f:
            return pickle.load(f)
    finally:
        if os.path.exists(res_path):
            os.remove(res_path)
        if os.path.exists(err_path):
            os.remove(err_path)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_code_runner.py -v`
Expected: PASS

- [ ] **Step 5: Commit（需用户授权）**

```bash
git add safety/sandbox.py tests/test_code_runner.py
git commit -m "feat(sandbox): add parent-side subprocess executor wrapper"
```

---

### Task 5: 端到端子进程测试

**Files:**
- Modify: `tests/test_code_runner.py`（追加真实子进程用例）

**Interfaces:**
- Consumes: `safety.sandbox.run_generated_code_subprocess`、`SandboxValidationError` / `SandboxExecError`、`core.config.CODE_EXEC_TIMEOUT`。

- [ ] **Step 1: Write the failing test**

在 `tests/test_code_runner.py` 追加（真实启动子进程，构造临时 CSV）：
```python
import pandas as pd

from safety.sandbox import run_generated_code_subprocess, SandboxValidationError, SandboxExecError


def _write_csv(tmp_path):
    p = tmp_path / "data.csv"
    pd.DataFrame({"region": ["a", "b", "a"], "sales_amount": [1, 2, 3]}).to_csv(p, index=False)
    return str(p)


def test_subprocess_normal_executes(tmp_path):
    path = _write_csv(tmp_path)
    code = "result_df = df.groupby('region', as_index=False)['sales_amount'].sum()"
    out = run_generated_code_subprocess(code, path, "csv", "pandas", timeout=30.0)
    assert out.to_dict(orient="records") == [
        {"region": "a", "sales_amount": 4},
        {"region": "b", "sales_amount": 2},
    ]


def test_subprocess_validation_failure(tmp_path):
    path = _write_csv(tmp_path)
    # 注意：clean_code 会去掉以 "import " 开头的行，故用不会被 strip 的 __import__() 形式触发校验失败
    with pytest.raises(SandboxValidationError):
        run_generated_code_subprocess("result_df = df.head(1)\n__import__('os')", path, "csv", "pandas", timeout=30.0)


def test_subprocess_runtime_error_retryable(tmp_path):
    path = _write_csv(tmp_path)
    with pytest.raises(SandboxExecError):
        run_generated_code_subprocess("result_df = df['nope']", path, "csv", "pandas", timeout=30.0)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_code_runner.py -v`
Expected: FAIL（若前序任务未实现则 AttributeError；若已实现则这些新用例应直接 PASS，说明实现已覆盖——此时视为通过，跳过 Step 3/4）

- [ ] **Step 3: Write minimal implementation**

本任务无新实现代码（依赖 Task 3/4 已完成）。若 Step 2 仍失败，回到 Task 3/4 修复子进程加载或父进程传参。

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_code_runner.py -v`
Expected: PASS（含 Task 3/4 的纯函数与 mock 用例，共 ~12 条）

- [ ] **Step 5: Commit（需用户授权）**

```bash
git add tests/test_code_runner.py
git commit -m "test(sandbox): add end-to-end subprocess execution tests"
```

---

### Task 6: 改造 `executors/base.py` 的 `execute`

**Files:**
- Modify: `executors/base.py:100-119`（`CodeExecutor.execute`）
- Test: `tests/test_executors_subprocess.py`（新建端到端 execute 测试）

**Interfaces:**
- Consumes: `safety.sandbox.run_generated_code_subprocess`、`SandboxValidationError`、`SandboxExecError`、`core.config.CODE_EXEC_TIMEOUT`。
- Produces: `CodeExecutor.execute` 返回结构不变（`rows / summary / error / terminal`）；父进程不再调用 `self.load_frame`。

- [ ] **Step 1: Write the failing test**

创建 `tests/test_executors_subprocess.py`：
```python
import pandas as pd
import pytest

from executors.pandas_executor import PandasExecutor


def _write_csv(tmp_path):
    p = tmp_path / "data.csv"
    pd.DataFrame({"region": ["a", "b", "a"], "sales_amount": [1, 2, 3]}).to_csv(p, index=False)
    return str(p)


def test_execute_uses_subprocess(tmp_path):
    path = _write_csv(tmp_path)
    state = {
        "input": {"file_path": path, "data_source_type": "csv", "user_question": "各region销售额"},
        "artifact": {"code": "result_df = df.groupby('region', as_index=False)['sales_amount'].sum()", "approved": True},
        "execution": {"retry_count": 0},
    }
    result = PandasExecutor().execute(state)
    assert result["error"] == ""
    assert result["terminal"] is False
    assert result["rows"] == [
        {"region": "a", "sales_amount": 4},
        {"region": "b", "sales_amount": 2},
    ]


def test_execute_validation_failure_terminal(tmp_path):
    path = _write_csv(tmp_path)
    state = {
        "input": {"file_path": path, "data_source_type": "csv", "user_question": "x"},
        # 注意：clean_code 会去掉以 "import " 开头的行，故用 __import__('os') 独立行触发校验失败
        "artifact": {"code": "result_df = df.head(1)\n__import__('os')", "approved": True},
        "execution": {"retry_count": 0},
    }
    result = PandasExecutor().execute(state)
    assert result["terminal"] is True
    assert "import" in result["error"].lower() or "生成代码" in result["error"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_executors_subprocess.py -v`
Expected: FAIL（`execute` 仍走进程内 `run_generated_code`，未触发子进程；或断言 `terminal=True` 失败）

- [ ] **Step 3: Write minimal implementation**

修改 `executors/base.py`：
1. 顶部 import 改为：
```python
from core.config import CODE_APPROVAL_ENABLED, CODE_EXEC_TIMEOUT
from safety.sandbox import (
    clean_code,
    run_generated_code_subprocess,
    SandboxValidationError,
    SandboxExecError,
)
```
2. 将 `CodeExecutor.execute` 替换为：
```python
def execute(self, state: dict) -> Dict[str, Any]:
    artifact = state.get("artifact", {}) or {}
    # 需要审批但被拒绝 = 终止性错误，不能继续 exec（与 SQL 执行器行为一致）
    if artifact.get("approval_required", False) and not artifact.get("approved", False):
        return {"error": "Code execution not approved.", "terminal": True}

    try:
        result_df = run_generated_code_subprocess(
            code=(state.get("artifact", {}) or {}).get("code", ""),
            file_path=_input(state)["file_path"],
            source_type=_input(state)["data_source_type"],
            executor_name=self.name,
            timeout=CODE_EXEC_TIMEOUT,
        )
    except SandboxValidationError as e:
        return {"error": str(e), "terminal": True}
    except SandboxExecError as e:
        return {"error": str(e), "terminal": False}

    return make_json_safe({
        "rows": result_df.to_dict(orient="records"),
        "summary": summarize_result(result_df),
        "error": "",
        "terminal": False,
    })
```
注意：`CodeExecutor` 不再在 `execute` 内调用 `self.load_frame`，`load_frame` / `extra_runtime_vars` 方法保留（供 `safety/code_runner.py` 按 executor_name 调用对应模块级 load 函数）。

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_executors_subprocess.py -v`
Expected: PASS

再运行全量后端测试，确认无退化：
Run: `pytest tests -q`
Expected: 全部 PASS（含原 81 条与新增用例）

- [ ] **Step 5: Commit（需用户授权）**

```bash
git add executors/base.py tests/test_executors_subprocess.py
git commit -m "refactor(executors): route code execution through subprocess sandbox"
```

---

### Task 7: 更新 `README.md`

**Files:**
- Modify: `README.md`（第 2 节环境变量表、第 9 节安全模型、第 12 节已知限制）

**Interfaces:**
- 无代码依赖，纯文档同步。

- [ ] **Step 1: Update 环境变量表（第 2 节）**

在环境变量表格末尾追加三行：
```markdown
| `CODE_EXEC_TIMEOUT` | 子进程执行代码的超时秒数，超时强制 kill | `30.0` |
| `CODE_EXEC_MEM_LIMIT_MB` | 子进程虚拟内存上限（MB），仅 Linux 生效 | `1024` |
| `CODE_EXEC_CPU_TIME` | 子进程 CPU 时间上限（秒），仅 Linux 生效 | `30` |
```

- [ ] **Step 2: Update 安全模型「代码执行」段（第 9 节）**

将「代码执行」段开头说明改为：
```markdown
**代码执行**（`safety/sandbox.py` + `safety/code_runner.py`）：LLM 生成的代码先清洗（去 markdown 代码块、import 行、中文引导语），
再做 AST 静态校验，最后在**独立子进程**中执行（父进程通过超时强制 kill）。

被拦截的行为（同前）：import / while / dunder / 危险内置 / 文件与网络 IO / 引用 os·sys·subprocess 等模块名。
```
并在该段末尾补充：
```markdown
**资源限制**：Linux 下子进程用 `resource.setrlimit` 限制虚拟内存（`RLIMIT_AS`）与 CPU 时间（`RLIMIT_CPU`）；
Windows 无 `resource` 模块，自动退化为仅超时保护。默认超时 30s。
```

- [ ] **Step 3: Update 已知限制（第 12 节）**

将「代码执行无限额」条目改为：
```markdown
- **代码执行已在独立子进程**：带超时（默认 30s）与 Linux 内存/CPU 限额；Windows 仅超时兜底，生产建议部署在 Linux 以获得内存限制。
```
并移除/改写「同进程内执行」相关表述（如第 9 节原有的"该沙箱没有 CPU / 内存 / 超时限制，且在同一进程内执行"提示）。

- [ ] **Step 4: Verify docs render**

Run: 人工浏览 `README.md` 第 2 / 9 / 12 节，确认表格与段落连贯、无残留旧描述。

- [ ] **Step 5: Commit（需用户授权）**

```bash
git add README.md
git commit -m "docs: document subprocess sandbox isolation and config knobs"
```

---

## Self-Review

**1. Spec coverage:**
- 独立子进程 + 超时 kill → Task 3/4/6 ✔
- 仅 Code 类 → Task 6 只改 `CodeExecutor.execute`，SQL 不动 ✔
- 子进程重新加载文件 → `code_runner._load_frame` ✔
- 超时 + Linux 限额（Windows 退化）→ Task 1 配置 + Task 3 `_apply_resource_limits` ✔
- 抽取 `_execute_code_impl`、保留 `run_generated_code` 供单测 → Task 2 ✔
- 错误分类 terminal → Task 2/3/4/6 ✔
- 接口契约不变 → Task 6 返回结构不变 ✔
- 测试（正常/校验失败/运行期/超时/崩溃）→ Task 3/4/5/6 ✔
- README 更新 → Task 7 ✔

**2. Placeholder scan:** 无 TBD/TODO；所有代码步骤均为完整实现。

**3. Type consistency:**
- `run_generated_code_subprocess(code, file_path, source_type, executor_name, timeout)` 在 Task 4 定义、Task 5/6 调用，签名一致。
- `SandboxValidationError` / `SandboxExecError` 在 Task 2 定义，Task 4/6 引用，名称一致。
- `code_runner.run(req, res_path, err_path)` 与 `__main__` 的 `argv[1..3]` 顺序（req/res/err）在 Task 3/4 一致。
- 临时文件前缀 `datapilot_req_/res_/err_` 在 Task 4 生成、`code_runner` 不假设文件名（由父进程传路径），无耦合冲突。

**4. 风险备注:** Task 5 端到端用例真实启动子进程，依赖 `python -m safety.code_runner` 能从项目根 import 模块；pytest 在项目根运行时 cwd 即为根，`-m` 自动加入 sys.path，Windows 下可跑通。
