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


@pytest.mark.parametrize(
    "code",
    [
        "result_df = df.head(1)\nx = str.__class__.__base__.__subclasses__()",
        "while True:\n    pass\nresult_df = df",
        "result_df = pd.read_csv('C:/secret.csv')",
        "result_df = df.to_csv('C:/out.csv')",
        "result_df = df.head(1)\n__import__('os')",
        "result_df = df.head(1)\nx = os.getcwd()",
    ],
)
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


from safety.sandbox import SandboxExecError, SandboxValidationError, _execute_code_impl


def test_impl_runtime_error_wrapped_as_exec_error():
    with pytest.raises(SandboxExecError):
        _execute_code_impl("result_df = df['missing_col']", {"df": _df(), "pd": pd})


def test_impl_validation_error_is_validation_type():
    # 注意：clean_code 会去掉 "import " 开头行，故用 __import__() 独立行触发校验
    with pytest.raises(SandboxValidationError):
        _execute_code_impl("result_df = df.head(1)\n__import__('os')", {"df": _df(), "pd": pd})
