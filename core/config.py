"""全局配置常量（可用环境变量覆盖）。"""

import os

from dotenv import load_dotenv

# 必须在读取任何配置之前加载 .env：本模块在导入时就计算常量，
# 若被其它模块先于 load_dotenv() 导入，配置会拿不到 .env 里的值。
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


# 超过该行数的数据源优先选择 Dask 执行器（与 planner 提示词保持一致）
DASK_ROW_THRESHOLD = _get_int("DASK_ROW_THRESHOLD", 50000)

# 执行结果统一截断行数
MAX_RESULT_ROWS = _get_int("MAX_RESULT_ROWS", 200)

# LLM 生成的代码是否需要人工审批后才执行
CODE_APPROVAL_ENABLED = _get_bool("CODE_APPROVAL_ENABLED", True)

# 单轮默认最大修复次数
DEFAULT_MAX_RETRIES = _get_int("DEFAULT_MAX_RETRIES", 1)

# focus_entities 最多保留的实体数量
MAX_FOCUS_ENTITIES = _get_int("MAX_FOCUS_ENTITIES", 5)

# LLM 调用遇到限流（429）/服务端临时故障时的重试策略
# 配额很低时（例如 RPM=3）调高 LLM_MAX_RETRIES，靠等待把请求排队跑完
LLM_MAX_RETRIES = _get_int("LLM_MAX_RETRIES", 4)
LLM_RETRY_BASE_DELAY = _get_float("LLM_RETRY_BASE_DELAY", 2.0)
LLM_RETRY_MAX_DELAY = _get_float("LLM_RETRY_MAX_DELAY", 30.0)

# 子进程执行生成的代码时，父进程等待的最大秒数（超时强制 kill）
CODE_EXEC_TIMEOUT = _get_float("CODE_EXEC_TIMEOUT", 30.0)

# 子进程虚拟内存上限（MB），仅 Linux 的 resource.setrlimit(RLIMIT_AS) 生效
CODE_EXEC_MEM_LIMIT_MB = _get_int("CODE_EXEC_MEM_LIMIT_MB", 1024)

# 子进程 CPU 时间上限（秒），仅 Linux 的 resource.setrlimit(RLIMIT_CPU) 生效
CODE_EXEC_CPU_TIME = _get_int("CODE_EXEC_CPU_TIME", 30)
