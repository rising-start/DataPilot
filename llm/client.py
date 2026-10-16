import logging
import os
import random
import re
import threading
import time
from functools import lru_cache

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

from agent.cancellation import CancellationError, current_cancel_event, run_blocking_with_cancel
from core.config import (
    LLM_MAX_RETRIES,
    LLM_REQUEST_TIMEOUT,
    LLM_RETRY_BASE_DELAY,
    LLM_RETRY_MAX_DELAY,
)
from llm.json_parse import extract_json_object

load_dotenv()

logger = logging.getLogger(__name__)

KIMI_API_KEY = os.getenv("KIMI_API_KEY")
KIMI_BASE_URL = os.getenv("KIMI_BASE_URL", "https://api.moonshot.cn/v1")


KIMI_MODEL = os.getenv("KIMI_MODEL", "kimi-k3")


_RETRYABLE_STATUS = {408, 429, 500, 502, 503, 504}

_RETRYABLE_EXC_NAMES = {
    "RateLimitError",
    "InternalServerError",
    "APITimeoutError",
    "APIConnectionError",
    "APIStatusError",
}
_RETRYABLE_TEXT_HINTS = (
    "rate limit",
    "rate_limit",
    "too many requests",
    "429",
    "overloaded",
    "temporarily unavailable",
    "timed out",
    "timeout",
)

_RETRY_AFTER_RE = re.compile(
    r"(?:try again after|retry after|retry-after|please retry)\s*[:=]?\s*(\d+(?:\.\d+)?)",
    re.IGNORECASE,
)


def _status_code(exc: BaseException) -> int | None:
    for obj in (exc, getattr(exc, "response", None)):
        code = getattr(obj, "status_code", None) or getattr(obj, "http_status", None)
        if isinstance(code, int):
            return code
    return None


def _suggested_delay(exc: BaseException) -> float | None:
    
    headers = getattr(getattr(exc, "response", None), "headers", None)
    if headers and hasattr(headers, "get"):
        for key in ("retry-after", "Retry-After", "retry-after-ms"):
            raw = headers.get(key)
            if raw is None:
                continue
            try:
                value = float(raw)
            except (TypeError, ValueError):
                continue
            return value / 1000.0 if key.endswith("-ms") else value

    match = _RETRY_AFTER_RE.search(str(exc))
    if match:
        try:
            return float(match.group(1))
        except ValueError:
            return None
    return None


def _is_retryable(exc: BaseException) -> bool:
    code = _status_code(exc)
    if code is not None:
        return code in _RETRYABLE_STATUS
    if type(exc).__name__ in _RETRYABLE_EXC_NAMES:
        return True
    text = str(exc).lower()
    return any(hint in text for hint in _RETRYABLE_TEXT_HINTS)


def _sleep(seconds: float) -> None:
    time.sleep(seconds)


def _backoff_delay(exc: BaseException, attempt: int) -> float:
    
    suggested = _suggested_delay(exc) or 0.0
    exponential = LLM_RETRY_BASE_DELAY * (2 ** (attempt - 1))
    delay = max(exponential, suggested)
    return min(delay, LLM_RETRY_MAX_DELAY) + random.uniform(0, 0.5)


def _invoke_with_retry(messages: list[dict[str, str]]) -> str:
    last_error: BaseException | None = None
    cancel_event = current_cancel_event()

    for attempt in range(LLM_MAX_RETRIES + 1):
        
        if cancel_event is not None and cancel_event.is_set():
            raise CancellationError("任务已取消")

        try:
            return run_blocking_with_cancel(_invoke_blocking, messages)
        except CancellationError:
            raise
        except Exception as exc:
            last_error = exc
            if attempt >= LLM_MAX_RETRIES or not _is_retryable(exc):
                raise

            delay = _backoff_delay(exc, attempt + 1)
            logger.warning(
                "LLM 调用失败（%s: %s），%.1fs 后第 %d/%d 次重试",
                type(exc).__name__,
                exc,
                delay,
                attempt + 1,
                LLM_MAX_RETRIES,
            )
            _sleep(delay)

    raise last_error  


@lru_cache(maxsize=1)
def get_llm() -> ChatOpenAI:
    if not KIMI_API_KEY:
        raise RuntimeError("缺少 KIMI_API_KEY，请检查环境变量或 .env 文件。")

    return ChatOpenAI(
        model=KIMI_MODEL,
        api_key=KIMI_API_KEY,
        base_url=KIMI_BASE_URL,
        temperature=1,
        
        request_timeout=LLM_REQUEST_TIMEOUT,
    )


def _invoke_blocking(messages: list[dict[str, str]]) -> str:
    resp = get_llm().invoke(messages)
    return resp.content if isinstance(resp.content, str) else str(resp.content)


def invoke_text(system_prompt: str, user_prompt: str) -> str:
    return _invoke_with_retry(
        [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
    )


def invoke_json(system_prompt: str, user_prompt: str) -> dict:
    return extract_json_object(invoke_text(system_prompt, user_prompt))
