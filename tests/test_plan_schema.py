from agent.support.plan_schema import coerce_plan


def test_keeps_valid_plan():
    plan = coerce_plan({
        "goal": "各地区销售额", "metrics": ["sales_amount"], "dimensions": ["region"],
        "filters": {"region": "华南"}, "tool": "pandas",
        "needs_chart": True, "chart_type": "bar", "reason": "r",
    })
    assert plan["tool"] == "pandas" and plan["chart_type"] == "bar"
    assert plan["metrics"] == ["sales_amount"]


def test_invalid_chart_type_becomes_none():
    assert coerce_plan({"chart_type": "radar"})["chart_type"] == "none"


def test_invalid_tool_is_dropped():
    assert coerce_plan({"tool": "spark"})["tool"] is None


def test_dirty_collections_are_cleaned():
    plan = coerce_plan({"metrics": ["a", 1, None], "dimensions": "region", "filters": []})
    assert plan["metrics"] == ["a"]
    assert plan["dimensions"] == []
    assert plan["filters"] == {}


def test_non_dict_input_yields_empty_plan():
    plan = coerce_plan(["not", "a", "dict"])
    assert plan["goal"] == "" and plan["needs_chart"] is False
