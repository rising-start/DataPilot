from agent.state import AgentState, merge_group, merge_run


def test_merge_group_keeps_untouched_keys():
    assert merge_group({"a": 1}, {"b": 2}) == {"a": 1, "b": 2}


def test_merge_group_replaces_same_key():
    assert merge_group({"a": 1, "b": 2}, {"b": 3}) == {"a": 1, "b": 3}


def test_merge_run_clears_error_when_not_set():
    assert merge_run({"error": "old", "logs": ["a"]}, {"logs": ["a", "b"]}) == {"error": "", "logs": ["a", "b"]}


def test_merge_run_keeps_explicit_error():
    assert merge_run({"error": "old"}, {"error": "new"}) == {"error": "new"}


def test_merge_handles_none():
    assert merge_group(None, {"a": 1}) == {"a": 1}
    assert merge_run(None, {"a": 1}) == {"a": 1, "error": ""}


def test_agent_state_groups_exist():
    for key in ("input", "dataset", "plan", "artifact", "execution", "output", "run"):
        assert key in AgentState.__annotations__


def test_run_group_uses_error_clearing_reducer():
    # run 分组必须用带 error 归零语义的 reducer，其余分组用普通浅合并
    assert AgentState.__annotations__["run"].__metadata__[0] is merge_run
    assert AgentState.__annotations__["plan"].__metadata__[0] is merge_group
