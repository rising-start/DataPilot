"""子进程执行入口：python -m safety.code_runner <req_json> <res_pkl> <err_json>

读取请求临时文件，按 executor_name 加载数据，执行生成的代码，
把结果（pickle）或错误（JSON）写回临时文件，并以退出码表达成败。
"""

import json
import sys

from core.config import CODE_EXEC_CPU_TIME, CODE_EXEC_MEM_LIMIT_MB
from safety.sandbox import SandboxValidationError, _execute_code_impl

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
    """静态校验失败（SandboxValidationError）视为终止性；其余（含运行期/归一化错误）可重试。"""
    return isinstance(exc, SandboxValidationError)


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
    with open(req_path, encoding="utf-8") as f:
        req = json.load(f)
    sys.exit(run(req, res_path, err_path))
