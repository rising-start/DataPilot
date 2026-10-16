"""全局配置常量（可用环境变量覆盖）。"""

import os

from dotenv import load_dotenv



load_dotenv()


def _get_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


def _get_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


def _get_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() not in {"0", "false", "no", "off"}



DASK_ROW_THRESHOLD = _get_int("DASK_ROW_THRESHOLD", 50000)


MAX_RESULT_ROWS = _get_int("MAX_RESULT_ROWS", 200)


CODE_APPROVAL_ENABLED = _get_bool("CODE_APPROVAL_ENABLED", True)


DEFAULT_MAX_RETRIES = _get_int("DEFAULT_MAX_RETRIES", 1)


MAX_FOCUS_ENTITIES = _get_int("MAX_FOCUS_ENTITIES", 5)


LLM_REPORT_ENABLED = _get_bool("LLM_REPORT_ENABLED", True)


LLM_REPORT_MAX_ROWS = _get_int("LLM_REPORT_MAX_ROWS", 30)



LLM_MAX_RETRIES = _get_int("LLM_MAX_RETRIES", 4)
LLM_RETRY_BASE_DELAY = _get_float("LLM_RETRY_BASE_DELAY", 2.0)
LLM_RETRY_MAX_DELAY = _get_float("LLM_RETRY_MAX_DELAY", 30.0)



LLM_REQUEST_TIMEOUT = _get_float("LLM_REQUEST_TIMEOUT", 120.0)


CODE_EXEC_TIMEOUT = _get_float("CODE_EXEC_TIMEOUT", 30.0)


CODE_EXEC_MEM_LIMIT_MB = _get_int("CODE_EXEC_MEM_LIMIT_MB", 1024)


CODE_EXEC_CPU_TIME = _get_int("CODE_EXEC_CPU_TIME", 30)



REDIS_URL = os.getenv("REDIS_URL", "")


REDIS_TASK_TTL = _get_int("REDIS_TASK_TTL", 0)
