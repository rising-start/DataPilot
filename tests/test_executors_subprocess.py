import pandas as pd

from executors.pandas_executor import PandasExecutor


def _write_csv(tmp_path):
    p = tmp_path / "data.csv"
    pd.DataFrame({"region": ["a", "b", "a"], "sales_amount": [1, 2, 3]}).to_csv(p, index=False)
    return str(p)


def test_execute_uses_subprocess(tmp_path):
    path = _write_csv(tmp_path)
    state = {
        "input": {"file_path": path, "data_source_type": "csv", "user_question": "各region销售额"},
        "artifact": {
            "code": "result_df = df.groupby('region', as_index=False)['sales_amount'].sum()",
            "approved": True,
        },
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
    # 注意：clean_code 会去掉以 "import " 开头的行，故用 __import__('os') 独立行触发校验失败
    state = {
        "input": {"file_path": path, "data_source_type": "csv", "user_question": "x"},
        "artifact": {"code": "result_df = df.head(1)\n__import__('os')", "approved": True},
        "execution": {"retry_count": 0},
    }
    result = PandasExecutor().execute(state)
    assert result["terminal"] is True
    assert "生成代码" in result["error"] or "import" in result["error"].lower()
