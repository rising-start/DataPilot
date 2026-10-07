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
    # 仅真正的静态校验失败（SandboxValidationError）视为终止性；
    # 普通 ValueError（如未赋值 result_df）不终止，应进 repair 重试
    assert code_runner._classify(code_runner.SandboxValidationError("生成代码不允许 import。")) is True


def test_classify_runtime_non_terminal():
    assert code_runner._classify(RuntimeError("代码执行出错: x")) is False


import subprocess

from safety.sandbox import (
    SandboxExecError,
    SandboxValidationError,
    run_generated_code_subprocess,
)


class _FakeProc:
    def __init__(self, returncode):
        self.returncode = returncode
        self.stderr = b""


def test_subprocess_validation_error_raises_validation(monkeypatch):
    def fake_run(*a, **k):
        return _FakeProc(returncode=1)

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr(
        "safety.sandbox._read_err_path",
        lambda p: {"error": "生成代码不允许 import。", "terminal": True},
    )
    with pytest.raises(SandboxValidationError):
        run_generated_code_subprocess("x", "f.csv", "csv", "pandas", timeout=5.0)


def test_subprocess_runtime_error_mock(monkeypatch):
    def fake_run(*a, **k):
        return _FakeProc(returncode=1)

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr(
        "safety.sandbox._read_err_path",
        lambda p: {"error": "代码执行出错: x", "terminal": False},
    )
    with pytest.raises(SandboxExecError):
        run_generated_code_subprocess("x", "f.csv", "csv", "pandas", timeout=5.0)


def test_subprocess_timeout_raises_exec_error(monkeypatch):
    def fake_run(*a, **k):
        raise subprocess.TimeoutExpired(cmd="x", timeout=5.0)

    monkeypatch.setattr(subprocess, "run", fake_run)
    with pytest.raises(SandboxExecError) as ei:
        run_generated_code_subprocess("x", "f.csv", "csv", "pandas", timeout=5.0)
    assert "超时" in str(ei.value)


import glob
import os
import tempfile

import pandas as pd


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
    # 注意：clean_code 会去掉以 "import " 开头的行，故用 __import__() 独立行触发校验失败
    path = _write_csv(tmp_path)
    with pytest.raises(SandboxValidationError):
        run_generated_code_subprocess("result_df = df.head(1)\n__import__('os')", path, "csv", "pandas", timeout=30.0)


def test_subprocess_runtime_error_retryable(tmp_path):
    path = _write_csv(tmp_path)
    with pytest.raises(SandboxExecError):
        run_generated_code_subprocess("result_df = df['nope']", path, "csv", "pandas", timeout=30.0)


def test_no_temp_files_leak_on_failure(tmp_path):
    # 断言失败路径不会在系统 temp 目录残留 datapilot_err_<token>.json
    base = tempfile.gettempdir()
    before = set(glob.glob(os.path.join(base, "datapilot_err_*.json")))
    path = _write_csv(tmp_path)
    with pytest.raises(SandboxValidationError):
        run_generated_code_subprocess(
            "result_df = df.head(1)\n__import__('os')", path, "csv", "pandas", timeout=30.0
        )
    after = set(glob.glob(os.path.join(base, "datapilot_err_*.json")))
    assert after == before, f"泄漏临时错误文件: {after - before}"
