# 沙箱子进程化设计（Sandbox Subprocess Isolation）

- 日期：2026-10-06
- 状态：已批准（待写实施计划）
- 范围：仅覆盖走 `safety.sandbox.run_generated_code` 的 Code 类执行器（pandas / dask），SQL 执行器不动。

## 1. 背景与动机

当前 `CodeExecutor.execute`（`executors/base.py:100`）在**父进程内**把 `df` / `pd` / `dd` 注入 globals 后直接 `exec`，由 `safety/sandbox.py` 的 `run_generated_code` 完成清洗 → AST 校验 → 执行 → 归一化。该实现无 CPU / 内存 / 超时限制，且在同一进程内执行（README 第 9、12 节已标注为最大安全隐患）。

本设计把"生成代码的执行"搬到一个**独立子进程**中，父进程通过超时强制 kill 来保证隔离与可控，从而闭合安全模型。

### 已确认的前提决策

| 项 | 决策 |
|---|---|
| 隔离机制 | 独立子进程（`subprocess`，跨平台超时 kill） |
| 覆盖范围 | 仅 Code 类（pandas / dask），SQL 保持现状 |
| 数据传入 | 子进程按 `file_path` 重新加载，父进程只传 code + 路径 + 类型 + executor 名 |
| 超时与限额 | 跨平台超时（默认 30s）+ 仅 Linux `resource.setrlimit`，Windows 退化为仅超时 |
| 测试契约 | 抽取内部实现 `_execute_code_impl`，保留进程内 `run_generated_code` 供单测，新增 subprocess 包装 |

## 2. 方案选型

子进程通信机制对比：

| 方案 | 做法 | 结论 |
|---|---|---|
| **A. subprocess + 临时文件传结果（采用）** | `subprocess.Popen([sys.executable, "-m", "safety.code_runner"])`，请求/结果走临时文件 | 纯标准库、跨平台稳、结果大小无 stdout 限制 |
| B. multiprocessing + Pipe | 用 Pipe/Queue 传参和结果 | Windows spawn + pickle 约束多，调试难 |
| C. 仅 stdin/stdout JSON | 请求和结果都走 stdout 一行 JSON | 易与日志/traceback 混流，datetime/numpy 需额外处理 |

采用方案 A。

## 3. 目标与验收标准

- 生成的 pandas / dask 代码在独立子进程中执行，子进程崩溃 / 超时不影响父进程。
- 父进程对执行超时（默认 30s）能强制终止并返回错误，不卡死。
- 静态校验失败（import / while / dunder / 禁调函数）标记为 `terminal=True`，不进入 repair 重试。
- 运行期错误 / 超时 / 内存超限 / 子进程崩溃标记为 `terminal=False`，进入现有 `repair_artifact` 重试。
- 现有 `executors/base.py::execute` 的对外签名与返回结构（`rows / summary / error / terminal`）不变，节点 / service / 前端无感。
- 现有 81 条后端单测不退化；新增子进程路径单测在本机（Windows）可跑通。
- Linux 下子进程受 `RLIMIT_AS` / `RLIMIT_CPU` 约束；Windows 无 `resource` 模块时自动退化为仅超时，不报错。

## 4. 组件与文件改动

### 4.1 新增 `safety/code_runner.py`

子进程入口模块，通过 `python -m safety.code_runner <req_json_path>` 启动。

职责：
1. 读取 `argv[1]` 指向的临时请求 JSON（`code` / `file_path` / `source_type` / `executor_name`）。
2. Linux 下在顶部设置资源限制：
   ```python
   try:
       import resource
       mb = CODE_EXEC_MEM_LIMIT_MB * 1024 * 1024
       resource.setrlimit(resource.RLIMIT_AS, (mb, mb))
       resource.setrlimit(resource.RLIMIT_CPU, (CODE_EXEC_CPU_TIME, CODE_EXEC_CPU_TIME))
   except ImportError:
       pass  # Windows 退化
   ```
3. 按 `executor_name` 调用对应模块级 load 函数：
   - `pandas` → `executors.pandas_executor.load_dataframe_by_type`
   - `dask` → `executors.dask_executor.load_dask_dataframe`
4. 构造 `variables = {"df": frame, "result_df": None}`，并叠加 `extra_runtime_vars()`（pandas 注入 `pd`；dask 注入 `dd` + `pd`）。
5. 调用 `safety.sandbox._execute_code_impl(code, variables)`。
6. 成功：把截断后的 `result_df` 以 pickle 写入约定结果文件 `res_<uuid>.pkl`，以退出码 0 结束。
7. 失败：把错误写入约定错误文件 `err_<uuid>.json`（`{"error": str, "terminal": bool}`），以非零退出码结束。
   - 静态校验失败（`validate_code` 抛 `ValueError`）→ `terminal=True`。
   - 运行期异常 → `terminal=False`。

结果 / 错误均通过临时文件（而非 stdout）回传，避免与日志、traceback 混流。父进程依据**退出码**区分成功（0）与失败（非 0），失败时再读 `err_<uuid>.json` 取 `error` 与 `terminal`。

### 4.2 重构 `safety/sandbox.py`

- **新增** `_execute_code_impl(code, variables) -> pd.DataFrame`：抽出原 `run_generated_code` 的核心逻辑（clean → `validate_code` → `exec` → `normalize_result`），不含任何进程边界。
- **保留** `run_generated_code(code, variables)`：进程内包装，调用 `_execute_code_impl`，专供现有单测。
- **新增** `run_generated_code_subprocess(code, file_path, source_type, executor_name, timeout) -> pd.DataFrame`：父进程侧。
  - 写请求临时 JSON `req_<uuid>.json`（含 code / file_path / source_type / executor_name），并约定 `res_<uuid>.pkl` / `err_<uuid>.json` 两个回传路径；
  - `subprocess.run([sys.executable, "-m", "safety.code_runner", req_path], timeout=timeout, ...)`；
  - 捕获 `subprocess.TimeoutExpired`：`Popen.kill()`，返回超时错误（message `"执行超时（>{}s）".format(timeout)`，`terminal=False`）；
  - 非零退出码（崩溃 / 子进程内异常）：读 `err_<uuid>.json`，返回其中 `error` 与 `terminal`（默认 `terminal=False`）；
  - 退出码 0：读 `res_<uuid>.pkl`（pickle 小 df）并返回；
  - `finally` 中删除 `req_/res_/err_` 三个临时文件，避免残留。
- `clean_code` / `validate_code` / `build_safe_globals` / `normalize_result` 保持不变（仍被 `_execute_code_impl` 调用，且单测直接依赖）。

### 4.3 `core/config.py`

新增：
- `CODE_EXEC_TIMEOUT: float = float(os.getenv("CODE_EXEC_TIMEOUT", "30.0"))`
- `CODE_EXEC_MEM_LIMIT_MB: int = int(os.getenv("CODE_EXEC_MEM_LIMIT_MB", "1024"))`（仅 Linux 生效）
- `CODE_EXEC_CPU_TIME: int = int(os.getenv("CODE_EXEC_CPU_TIME", "30"))`（仅 Linux 生效）

### 4.4 `executors/base.py`

`CodeExecutor.execute` 改动：
- **不再在父进程调用 `self.load_frame(state)`**；load 下移到子进程。
- 改为：
  ```python
  result_df = run_generated_code_subprocess(
      code=artifact["code"],
      file_path=_input(state)["file_path"],
      source_type=_input(state)["data_source_type"],
      executor_name=self.name,
      timeout=CODE_EXEC_TIMEOUT,
  )
  ```
- 返回结构 `rows / summary / error / terminal` 维持不变；把子进程透传的 `terminal` 标志写入返回。
- `load_frame` / `extra_runtime_vars` 方法**保留**（供子进程按 `executor_name` 调用对应模块级 load 函数），不删除。

### 4.5 错误处理与重试衔接

| 失败类型 | 触发 | terminal | 后续 |
|---|---|---|---|
| 静态校验失败 | `validate_code` 抛 `ValueError`（import / while / dunder / 禁调函数 / 禁 IO 方法） | `True` | 不重试，直接进 `error` 节点 |
| 运行期错误 / 超时 / 内存超限 / 子进程崩溃 | exec 抛异常、父进程 timeout kill、`RLIMIT` 触发、非零退出码 | `False` | 进入现有 `repair_artifact` 重试（受 `DEFAULT_MAX_RETRIES` 限制） |

`run_generated_code_subprocess` 把子进程返回的 `terminal` 标志透传到 `execute` 的返回 dict。

## 5. 数据流（端到端）

```
CodeExecutor.execute (父进程)
  └─ run_generated_code_subprocess(code, file_path, source_type, executor_name, timeout)
       ├─ 写请求临时 JSON
       ├─ subprocess.Popen([py, -m, safety.code_runner, req_path], timeout)
       │    子进程:
       │      ├─ setrlimit (Linux only)
       │      ├─ 按 executor_name 加载 frame
       │      ├─ _execute_code_impl(code, {df, result_df, pd[, dd]})
       │      └─ 结果 pickle → 临时文件 / 错误 JSON
       ├─ 读结果临时文件 → 返回 pd.DataFrame
       └─ 删除临时文件
  └─ make_json_safe({rows, summary, error, terminal})
```

## 6. 测试策略

- **保留**现有 `safety/` 单测对 `run_generated_code` / `validate_code` 的 6 类恶意代码拦截；`executors` 相关单测不变（走进程内函数或 `FakeExecutor`）。
- **新增** `safety/test_code_runner.py`：
  - 正常代码经子进程返回正确 df（断言行列与值）；
  - 静态校验失败（含 `import`）→ `terminal=True`；
  - 运行期错误（如列不存在）→ `terminal=False`；
  - 超时：用 `@patch("subprocess.run", side_effect=subprocess.TimeoutExpired(...))` 断言返回超时错误且 `terminal=False`；
  - 子进程非零退出（模拟崩溃）→ 父进程返回 error、`terminal=False`；
  - Linux `setrlimit` 分支用平台检测断言（Windows 退化路径不报错）。

所有子进程测试须在本机（Windows）跑通。

## 7. 接口契约与回归

- `CodeExecutor.execute` 签名与返回结构不变，上层节点 / service / 前端无感。
- 代价：每次 `execute` 多一次进程启动（约百毫秒）+ 子进程重新 load 文件一次。对大文件更必要，可接受。进程池复用解释器列为后续优化（本期不做，YAGNI）。
- Windows 注意：`subprocess` 用 spawn，子进程以 `python -m safety.code_runner` 从项目根启动，继承 cwd / sys.path，能正常 import 项目模块。

## 8. 配置项汇总

| 变量 | 默认 | 说明 |
|---|---|---|
| `CODE_EXEC_TIMEOUT` | `30.0` | 父进程等待子进程的最大秒数，超时强制 kill |
| `CODE_EXEC_MEM_LIMIT_MB` | `1024` | 子进程虚拟内存上限（仅 Linux `RLIMIT_AS` 生效） |
| `CODE_EXEC_CPU_TIME` | `30` | 子进程 CPU 时间上限秒（仅 Linux `RLIMIT_CPU` 生效） |

## 9. 风险与权衡

- 子进程重新加载文件带来一次额外磁盘 IO；大文件下这是必要代价。
- Windows 无 `resource` 模块，仅超时兜底，挡不住内存炸裂类劣质代码；生产建议部署在 Linux 以获得内存/CPU 限制。
- `RLIMIT_AS` 限制虚拟内存，设过小会影响 pandas 加载大文件，故默认给足 1GB。
- 临时文件需确保用完即删，避免进程异常退出残留（父进程 finally 中删除）。

## 10. 后续可选项（非本期）

- 子进程池复用解释器降低启动开销。
- 把 SQL 执行器也纳入同一子进程 runner。
- 用临时 Docker 容器做更强隔离（本期未采用）。
