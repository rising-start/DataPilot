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
