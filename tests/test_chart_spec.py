import pandas as pd

import viz.chart
from viz.chart import build_chart_spec


def _df():
    return pd.DataFrame({
        "channel": ["线上", "线下"],
        "sales_amount": [10.0, 20.0],
        "order_count": [1, 2],
    })


def test_series_uses_plan_metrics_when_present():
    spec = build_chart_spec(_df(), {"chart_type": "bar", "metrics": ["sales_amount", "order_count"]})
    assert spec["series"] == ["sales_amount", "order_count"]
    assert spec["x"] == "channel"


def test_series_falls_back_to_metric_column():
    spec = build_chart_spec(_df(), {"chart_type": "bar"})
    assert spec["series"] == ["sales_amount"]


def test_no_numeric_column_yields_none():
    spec = build_chart_spec(pd.DataFrame({"channel": ["a"]}), {"chart_type": "bar"})
    assert spec["chart_type"] == "none"
    assert spec["series"] == []


def test_pie_keeps_single_series():
    spec = build_chart_spec(_df(), {"chart_type": "pie"})
    assert spec["chart_type"] == "pie" and len(spec["series"]) == 1


def test_build_chart_figure_removed():
    assert not hasattr(viz.chart, "build_chart_figure")
