import subprocess
import sys

import executors
from executors.base import BaseExecutor
from executors.registry import get_executor, list_executors


class DummyExecutor(BaseExecutor):
    name = "dummy"

    def supports(self, state):
        return True

    def generate(self, state):
        return {"code": "", "kind": "dummy", "error": ""}

    def execute(self, state):
        return {"rows": [], "summary": {}, "error": "", "terminal": False}


def test_custom_executor_can_be_registered():
    executors.register_executor(DummyExecutor(generator_prompt="g", repair_prompt="r", artifact_kind="dummy"))
    assert "dummy" in list_executors()
    assert get_executor("dummy").name == "dummy"


def test_prompts_are_injected():
    executors.init_executors()
    executor = get_executor("pandas")
    assert executor.generator_prompt and executor.repair_prompt
    assert executor.artifact_kind == "pandas"


def test_executors_do_not_import_agent_prompts():
    # 只导入执行器模块时，agent.prompts 不应出现在 sys.modules
    code = (
        "import sys; "
        "import executors.sql_executor, executors.pandas_executor; "
        "assert 'agent.prompts' not in sys.modules"
    )
    assert subprocess.call([sys.executable, "-c", code]) == 0
