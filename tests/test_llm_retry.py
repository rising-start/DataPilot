import pytest

from llm import client as llm_client


class _FakeResponse:
    def __init__(self, status_code: int, headers=None):
        self.status_code = status_code
        self.headers = headers or {}


class _FakeContent:
    def __init__(self, content: str):
        self.content = content


class _HttpError(Exception):
    """模拟 openai 的 APIStatusError：带 status_code 与 response。"""

    def __init__(self, status_code: int, message: str = "boom", headers=None):
        super().__init__(message)
        self.status_code = status_code
        self.response = _FakeResponse(status_code, headers)


class _FakeLLM:
    def __init__(self, failures: int, error_factory=None):
        self.failures = failures
        self.error_factory = error_factory or (lambda: _HttpError(429))
        self.calls = 0

    def invoke(self, messages):
        self.calls += 1
        if self.calls <= self.failures:
            raise self.error_factory()
        return _FakeContent("ok")


@pytest.fixture
def sleep_calls(monkeypatch):
    calls = []
    monkeypatch.setattr(llm_client, "_sleep", lambda seconds: calls.append(seconds))
    monkeypatch.setattr(llm_client, "LLM_RETRY_BASE_DELAY", 1.0)
    monkeypatch.setattr(llm_client, "LLM_RETRY_MAX_DELAY", 30.0)
    return calls


def _patch_llm(monkeypatch, fake):
    monkeypatch.setattr(llm_client, "get_llm", lambda: fake)


def test_retry_then_success(monkeypatch, sleep_calls):
    monkeypatch.setattr(llm_client, "LLM_MAX_RETRIES", 3)
    fake = _FakeLLM(failures=2)
    _patch_llm(monkeypatch, fake)

    assert llm_client.invoke_text("sys", "user") == "ok"
    assert fake.calls == 3
    assert len(sleep_calls) == 2
    # 指数退避：第二次等待不小于第一次
    assert sleep_calls[1] >= sleep_calls[0]


def test_give_up_after_max_retries(monkeypatch, sleep_calls):
    monkeypatch.setattr(llm_client, "LLM_MAX_RETRIES", 2)
    fake = _FakeLLM(failures=99)
    _patch_llm(monkeypatch, fake)

    with pytest.raises(_HttpError):
        llm_client.invoke_text("sys", "user")

    assert fake.calls == 3          # 首次 + 2 次重试
    assert len(sleep_calls) == 2


def test_non_retryable_error_raises_immediately(monkeypatch, sleep_calls):
    monkeypatch.setattr(llm_client, "LLM_MAX_RETRIES", 5)
    fake = _FakeLLM(failures=99, error_factory=lambda: _HttpError(401, "invalid auth"))
    _patch_llm(monkeypatch, fake)

    with pytest.raises(_HttpError):
        llm_client.invoke_text("sys", "user")

    assert fake.calls == 1
    assert sleep_calls == []


def test_missing_api_key_is_not_retried(monkeypatch, sleep_calls):
    monkeypatch.setattr(llm_client, "LLM_MAX_RETRIES", 5)

    def _boom():
        raise RuntimeError("缺少 KIMI_API_KEY，请检查环境变量或 .env 文件。")

    monkeypatch.setattr(llm_client, "get_llm", _boom)

    with pytest.raises(RuntimeError):
        llm_client.invoke_text("sys", "user")

    assert sleep_calls == []


def test_retry_after_header_is_honored(monkeypatch, sleep_calls):
    monkeypatch.setattr(llm_client, "LLM_MAX_RETRIES", 1)
    fake = _FakeLLM(failures=1, error_factory=lambda: _HttpError(429, headers={"Retry-After": "7"}))
    _patch_llm(monkeypatch, fake)

    assert llm_client.invoke_text("sys", "user") == "ok"
    assert sleep_calls[0] >= 7


def test_retry_after_hint_in_message_is_honored(monkeypatch, sleep_calls):
    monkeypatch.setattr(llm_client, "LLM_MAX_RETRIES", 1)

    def _factory():
        return _HttpError(429, "request reached organization max RPM: 3, please try again after 5 seconds")

    fake = _FakeLLM(failures=1, error_factory=_factory)
    _patch_llm(monkeypatch, fake)

    assert llm_client.invoke_text("sys", "user") == "ok"
    assert sleep_calls[0] >= 5
