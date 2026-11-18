"""A request that never left the host gets its own retry budget (#6636)."""

import asyncio
import errno
import socket

import pytest

from praisonaiagents.llm import llm as llm_module
from praisonaiagents.llm.error_classifier import _is_unreachable
from praisonaiagents.llm.llm import LLM


def _dns_error():
    try:
        raise socket.gaierror(-3, "Temporary failure in name resolution")
    except socket.gaierror as cause:
        try:
            raise Exception("Connection error.") from cause
        except Exception as wrapped:
            return wrapped


@pytest.mark.parametrize("error", [
    _dns_error(),
    OSError(errno.ENETUNREACH, "Network is unreachable"),
    Exception("getaddrinfo ENOTFOUND api.openai.com"),
])
def test_unreachable_detected(error):
    assert _is_unreachable(error)


@pytest.mark.parametrize("error", [
    ConnectionRefusedError("Connection refused"),
    ConnectionResetError("Connection reset by peer"),
    Exception("503 Service Unavailable"),
    type("APIError", (Exception,), {"status_code": 502})("upstream: no route to host"),
])
def test_other_errors_not_unreachable(error):
    assert not _is_unreachable(error)


def _flaky(failures, error_factory):
    calls = {"n": 0}

    def completion(**kwargs):
        calls["n"] += 1
        if calls["n"] <= failures:
            raise error_factory()
        return "done"

    return completion, calls


def test_outage_outlasts_max_retries(monkeypatch):
    sleeps = []
    monkeypatch.setattr(llm_module.time, "sleep", sleeps.append)
    llm = LLM(model="fake")
    completion, calls = _flaky(6, _dns_error)  # more than max_retries=3
    assert llm._call_with_retry(completion) == "done"
    assert calls["n"] == 7
    assert sleeps == [2.0, 4.0, 8.0, 16.0, 30.0, 30.0]


def test_budget_exhausted_falls_back_to_general_policy(monkeypatch):
    monkeypatch.setattr(llm_module.time, "sleep", lambda s: None)
    llm = LLM(model="fake", network_retry_budget=0)
    completion, calls = _flaky(100, _dns_error)
    with pytest.raises(Exception, match="Connection error"):
        llm._call_with_retry(completion)
    assert calls["n"] <= llm._max_retries + 1


def test_server_errors_keep_general_budget(monkeypatch):
    monkeypatch.setattr(llm_module.time, "sleep", lambda s: None)
    llm = LLM(model="fake")
    completion, calls = _flaky(100, lambda: Exception("503 Service Unavailable"))
    with pytest.raises(Exception, match="503"):
        llm._call_with_retry(completion)
    assert calls["n"] == llm._max_retries + 1


def test_async_outage_outlasts_max_retries(monkeypatch):
    sleeps = []

    async def fake_sleep(s):
        sleeps.append(s)

    monkeypatch.setattr(llm_module.asyncio, "sleep", fake_sleep)
    llm = LLM(model="fake")
    sync_completion, calls = _flaky(5, _dns_error)

    async def completion(**kwargs):
        return sync_completion(**kwargs)

    assert asyncio.run(llm._call_with_retry_async(completion)) == "done"
    assert calls["n"] == 6
    assert sleeps == [2.0, 4.0, 8.0, 16.0, 30.0]


class _Clock:
    """Fake monotonic clock advanced by each (fake) sleep."""

    def __init__(self):
        self.now = 1000.0
        self.sleeps = []

    def monotonic(self):
        return self.now

    def sleep(self, s):
        self.sleeps.append(s)
        self.now += s


def test_budget_expiry_returns_to_general_limit(monkeypatch):
    clock = _Clock()
    monkeypatch.setattr(llm_module.time, "monotonic", clock.monotonic)
    monkeypatch.setattr(llm_module.time, "sleep", clock.sleep)
    llm = LLM(model="fake", network_retry_budget=10)
    completion, calls = _flaky(1000, _dns_error)
    with pytest.raises(Exception, match="Connection error"):
        llm._call_with_retry(completion)
    assert clock.sleeps[:3] == [2.0, 4.0, 4.0]  # last wait is cut to the deadline
    assert calls["n"] <= 4 + llm._max_retries + 1  # then the general limit applies


def test_async_budget_expiry_returns_to_general_limit(monkeypatch):
    clock = _Clock()

    async def fake_sleep(s):
        clock.sleep(s)

    monkeypatch.setattr(llm_module.time, "monotonic", clock.monotonic)
    monkeypatch.setattr(llm_module.asyncio, "sleep", fake_sleep)
    llm = LLM(model="fake", network_retry_budget=10)
    sync_completion, calls = _flaky(1000, _dns_error)

    async def completion(**kwargs):
        return sync_completion(**kwargs)

    with pytest.raises(Exception, match="Connection error"):
        asyncio.run(llm._call_with_retry_async(completion))
    assert clock.sleeps[:3] == [2.0, 4.0, 4.0]
    assert calls["n"] <= 4 + llm._max_retries + 1


def test_budget_setting_not_sent_to_provider():
    llm = LLM(model="gpt-4o-mini", network_retry_budget=0)
    assert "network_retry_budget" not in llm._build_completion_params()


def test_network_retry_emits_retry_callback(monkeypatch):
    from praisonaiagents import main as main_module

    events = []
    monkeypatch.setattr(main_module, "execute_sync_callback",
                        lambda display_type, **kw: events.append((display_type, kw)))
    monkeypatch.setattr(llm_module.time, "sleep", lambda s: None)
    llm = LLM(model="fake")
    completion, _ = _flaky(2, _dns_error)
    assert llm._call_with_retry(completion) == "done"
    assert [(t, kw["attempt"], kw["max_attempts"]) for t, kw in events] == [
        ("retry", 1, None), ("retry", 2, None)]
