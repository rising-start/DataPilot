"""LLM 生成代码的清洗、静态校验与受限执行。

说明：这里的 exec 属于“降低风险”而非“绝对隔离”。
生成代码只拿到最小内置函数集合，且经过 AST 校验，
但没有 CPU/内存/超时限制；生产部署建议改为独立子进程执行。
"""

from __future__ import annotations

import ast
import re
import time
from typing import Any

import pandas as pd

from agent.cancellation import CancellationError

from core.config import MAX_RESULT_ROWS

_ALLOWED_BUILTINS: dict[str, Any] = {
    "abs": abs,
    "all": all,
    "any": any,
    "bool": bool,
    "dict": dict,
    "enumerate": enumerate,
    "float": float,
    "int": int,
    "isinstance": isinstance,
    "len": len,
    "list": list,
    "max": max,
    "min": min,
    "range": range,
    "round": round,
    "set": set,
    "sorted": sorted,
    "str": str,
    "sum": sum,
    "tuple": tuple,
    "zip": zip,
}

# 生成代码中不允许出现的模块名（防止借助注入的 pd/dd 回溯到这些模块）
_FORBIDDEN_NAMES = {
    "os",
    "sys",
    "subprocess",
    "socket",
    "shutil",
    "pathlib",
    "requests",
    "urllib",
    "pickle",
    "importlib",
    "builtins",
    "globals",
    "locals",
    "vars",
}

# 生成代码中不允许调用的函数名
_FORBIDDEN_CALLS = {
    "open",
    "eval",
    "exec",
    "compile",
    "__import__",
    "input",
    "getattr",
    "setattr",
    "delattr",
    "dir",
    "exit",
    "quit",
    "breakpoint",
    "help",
}

# 禁止通过注入的 pd / dd 做文件读写或网络访问
_FORBIDDEN_IO_METHODS = {
    "read_csv",
    "read_excel",
    "read_table",
    "read_fwf",
    "read_json",
    "read_html",
    "read_pickle",
    "read_parquet",
    "read_feather",
    "read_orc",
    "read_hdf",
    "read_sql",
    "read_sql_query",
    "read_sql_table",
    "read_clipboard",
    "read_gbq",
    "to_csv",
    "to_excel",
    "to_json",
    "to_pickle",
    "to_parquet",
    "to_feather",
    "to_hdf",
    "to_sql",
    "to_clipboard",
}


def clean_code(code: str) -> str:
    """去掉 markdown 代码块、import 行和中文引导语。"""
    code = (code or "").strip()

    fenced = re.search(r"```(?:python|py)?\s*(.*?)\s*```", code, re.DOTALL | re.IGNORECASE)
    if fenced:
        code = fenced.group(1).strip()

    kept_lines = []
    for line in code.splitlines():
        stripped = line.strip()

        if stripped.startswith("import "):
            continue
        if stripped.startswith("from ") and " import " in stripped:
            continue
        if stripped.startswith(("下面是", "这是", "以下是", "说明：", "注意：")):
            continue

        kept_lines.append(line)

    return "\n".join(kept_lines).strip()


def validate_code(code: str) -> None:
    """对生成代码做静态校验，不合规直接抛 ValueError。"""
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        raise ValueError(f"生成代码存在语法错误: {e}") from e

    for node in ast.walk(tree):
        # 不允许导入任何模块
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            raise ValueError("生成代码不允许 import。")

        # 不允许 while 循环（避免生成死循环拖死进程）
        if isinstance(node, ast.While):
            raise ValueError("生成代码不允许 while 循环。")

        # 不允许访问 dunder 属性（阻断 str.__class__.__base__.__subclasses__() 这类逃逸）
        if isinstance(node, ast.Attribute) and node.attr.startswith("__"):
            raise ValueError(f"生成代码不允许访问属性 {node.attr}。")

        if isinstance(node, ast.Name):
            if node.id.startswith("__"):
                raise ValueError(f"生成代码不允许引用 {node.id}。")
            if node.id in _FORBIDDEN_NAMES:
                raise ValueError(f"生成代码不允许引用模块 {node.id}。")

        if isinstance(node, ast.Call):
            func = node.func
            name = getattr(func, "id", None) or getattr(func, "attr", None)
            if name in _FORBIDDEN_CALLS:
                raise ValueError(f"生成代码不允许调用 {name}()。")
            if isinstance(func, ast.Attribute) and func.attr in _FORBIDDEN_IO_METHODS:
                raise ValueError(f"生成代码不允许进行文件/网络 IO：{func.attr}()。")


def build_safe_globals(extra: dict[str, Any] | None = None) -> dict[str, Any]:
    """每次执行都新建一份 globals，避免跨请求污染。"""
    namespace: dict[str, Any] = {"__builtins__": dict(_ALLOWED_BUILTINS)}
    if extra:
        namespace.update(extra)
    return namespace


def normalize_result(result: Any) -> pd.DataFrame:
    """把执行结果统一成截断后的 pandas DataFrame。"""
    if result is None:
        raise ValueError("生成代码必须把最终结果赋值给 result_df。")

    # Dask DataFrame -> pandas DataFrame
    if hasattr(result, "compute"):
        result = result.compute()

    if isinstance(result, pd.Series):
        series_name = result.name or "value"
        result = result.reset_index(name=series_name)

    if not isinstance(result, pd.DataFrame):
        raise ValueError("result_df 必须是 pandas DataFrame 或 Series。")

    return result.head(MAX_RESULT_ROWS).copy()


class SandboxValidationError(ValueError):
    """静态校验失败（import / while / dunder / 禁调函数等）：终止性错误，不应重试。"""


class SandboxExecError(RuntimeError):
    """运行期执行错误 / 超时 / 子进程崩溃：可重试。"""


def _execute_code_impl(code: str, variables: dict[str, Any] | None = None) -> pd.DataFrame:
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


def run_generated_code(code: str, variables: dict[str, Any] | None = None) -> pd.DataFrame:
    """进程内执行（保留供现有单测与遗留调用）。"""
    return _execute_code_impl(code, variables)


def _read_err_path(err_path: str) -> dict[str, Any]:
    import json
    try:
        with open(err_path, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"error": "子进程异常退出（无错误详情）", "terminal": False}


def run_generated_code_subprocess(
    code: str,
    file_path: str,
    source_type: str,
    executor_name: str,
    timeout: float,
    cancel_event=None,
) -> pd.DataFrame:
    """在独立子进程中执行生成的代码，返回截断后的 DataFrame。

    成功 -> 返回 DataFrame；
    子进程校验失败 -> 抛 SandboxValidationError（terminal）；
    子进程运行期错误 / 超时 / 崩溃 -> 抛 SandboxExecError（可重试）。
    执行期间轮询 `cancel_event`：一旦被取消，立即 kill 子进程并抛 CancellationError，
    让上层把任务状态置为 cancelled。
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
        try:
            proc = subprocess.Popen(
                [sys.executable, "-m", "safety.code_runner", req_path, res_path, err_path],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
            )
            deadline = time.monotonic() + timeout
            poll_interval = 0.2
            while True:
                try:
                    proc.wait(timeout=poll_interval)
                    break
                except subprocess.TimeoutExpired:
                    if cancel_event is not None and cancel_event.is_set():
                        proc.kill()
                        proc.wait()
                        raise CancellationError("任务已取消") from None
                    if time.monotonic() >= deadline:
                        proc.kill()
                        proc.wait()
                        raise SandboxExecError(f"执行超时（>{timeout}s），已强制终止。") from None
        except CancellationError:
            raise
        except subprocess.TimeoutExpired:  # pragma: no cover - 理论上已被上面的循环捕获
            raise SandboxExecError(f"执行超时（>{timeout}s），已强制终止。") from None

        if proc.returncode != 0:
            err = _read_err_path(err_path)
            # Popen 下 proc.stderr 是管道对象（非 bytes），进程已结束后读取即可
            detail = ""
            if proc.stderr is not None:
                detail = proc.stderr.read().decode("utf-8", "replace").strip()
            if bool(err.get("terminal", False)):
                msg = err.get("error", "代码校验失败。")
                raise SandboxValidationError(msg + _stderr_suffix(detail))
            msg = err.get("error", "子进程执行失败。")
            raise SandboxExecError(msg + _stderr_suffix(detail))

        try:
            with open(res_path, "rb") as f:
                return pickle.load(f)
        except (pickle.UnpicklingError, EOFError, OSError) as e:
            raise SandboxExecError(f"读取子进程结果失败：{e}") from e
    finally:
        # 覆盖全部分支（成功 / 校验失败 / 运行期错误 / 超时）：统一清理三份临时文件
        for p in (req_path, res_path, err_path):
            if os.path.exists(p):
                try:
                    os.remove(p)
                except OSError:
                    pass


def _stderr_suffix(detail: str) -> str:
    """把子进程 stderr 片段附到错误信息后，便于排查失败原因。"""
    if not detail:
        return ""
    return "\n子进程 stderr: " + detail[-2000:]
