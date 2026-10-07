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
