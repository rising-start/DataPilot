"""进度上报机制测试：task_id 注入图状态 + 注册表派发。

不依赖 LLM：用 fake 图替换真实 LangGraph，仅验证"阶段上报被正确接线"。
"""
from unittest import mock

from agent.progress import register_progress, report_progress
from service import AnalysisService


def test_report_progress_uses_registry():
    calls: list[str] = []
    register_progress("t1", calls.append)
    try:
        report_progress({"run": {"task_id": "t1"}}, "load")
        assert calls == ["load"]
    finally:
        from agent.progress import unregister_progress

        unregister_progress("t1")


def test_report_progress_skips_without_callback():
    # 无 task_id / 未注册 / 非 dict 都不应抛错
    report_progress({"run": {}}, "load")
    report_progress({}, "load")
    report_progress("not-a-dict", "load")
    register_progress("t2", lambda s: None)
    try:
        report_progress({"run": {"task_id": "t2"}}, "load")  # 回调为空操作
    finally:
        from agent.progress import unregister_progress

        unregister_progress("t2")


def test_start_analysis_injects_task_id():
    fake = mock.MagicMock()
    captured: dict = {}

    def fake_invoke(state, config=None):
        captured["state"] = state
        return {}

    fake.invoke = fake_invoke

    svc = AnalysisService(graph=fake)
    svc.start_analysis("p", "csv", "q", task_id="t1")
    assert captured["state"]["run"]["task_id"] == "t1"


def test_resume_injects_task_id_via_command():
    fake = mock.MagicMock()
    captured: dict = {}

    def fake_invoke(cmd, config=None):
        captured["cmd"] = cmd
        return {}

    fake.invoke = fake_invoke

    svc = AnalysisService(graph=fake)
    svc.resume("tid", True, task_id="t1")
    assert captured["cmd"].resume is True
    assert captured["cmd"].update["run"]["task_id"] == "t1"
