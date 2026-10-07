from core.config import CODE_EXEC_CPU_TIME, CODE_EXEC_MEM_LIMIT_MB, CODE_EXEC_TIMEOUT


def test_subprocess_config_defaults():
    assert CODE_EXEC_TIMEOUT == 30.0
    assert CODE_EXEC_MEM_LIMIT_MB == 1024
    assert CODE_EXEC_CPU_TIME == 30
