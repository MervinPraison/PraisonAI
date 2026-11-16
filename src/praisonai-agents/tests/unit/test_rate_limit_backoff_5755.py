"""Headerless rate limits use existing jitter unless the caller selected a delay."""
import asyncio
from unittest.mock import AsyncMock

import pytest

from praisonaiagents.llm.llm import LLM


@pytest.mark.parametrize("attempt,expected", [(1, 3), (2, 9), (3, 27), (10, 60)])
def test_explicit_none_and_attempt_cap(monkeypatch, attempt, expected):
    """None selects jitter with the same one-based attempts and 60-second cap."""
    llm = LLM(model="openai/gpt-4o-mini", retry_delay=None)
    monkeypatch.setattr("praisonaiagents.llm.error_classifier.random.uniform", lambda low, high: high)
    decision = llm.resolve_failover_decision(RateLimited(), {"attempt": attempt, "max_retries": 20})
    assert decision.backoff_ms == expected * 1000


class RateLimited(Exception):
    """Provider-like exception exposing the authoritative HTTP response."""
    status_code = 429

    def __init__(self, headers=None):
        super().__init__("rate limited")
        self.response = type("Response", (), {"headers": headers or {}})()


@pytest.mark.parametrize("is_async", [False, True])
@pytest.mark.parametrize("delay,headers,expected", [
    (None, {}, [3, 9, 27]),
    (7, {}, [7, 7, 7]),
    (0, {}, [0, 0, 0]),
    (None, {"retry-after": "2"}, [2, 2, 2]),
    (7, {"retry-after": "2"}, [2, 2, 2]),
    (None, {"retry-after": "0"}, [0, 0, 0]),
    (None, {"retry-after": "99999"}, [300, 300, 300]),
])
def test_actual_retry_loop_delay_selection(monkeypatch, is_async, delay, headers, expected):
    """Drive sync/async retry loops without sleeping or contacting any provider."""
    kwargs = {} if delay is None else {"retry_delay": delay}
    llm = LLM(model="openai/gpt-4o-mini", **kwargs)
    monkeypatch.setattr("praisonaiagents.llm.error_classifier.random.uniform", lambda low, high: high)
    sleeps = []
    error = RateLimited(headers)
    if is_async:
        async def sleep(seconds):
            sleeps.append(seconds)
        monkeypatch.setattr("praisonaiagents.llm.llm.asyncio.sleep", sleep)
        fail = AsyncMock(side_effect=error)
        with pytest.raises(RateLimited):
            asyncio.run(llm._call_with_retry_async(fail))
        assert fail.await_count == llm._max_retries + 1
    else:
        monkeypatch.setattr("praisonaiagents.llm.llm.time.sleep", sleeps.append)
        calls = []
        def fail():
            calls.append(True)
            raise error
        with pytest.raises(RateLimited):
            llm._call_with_retry(fail)
        assert len(calls) == llm._max_retries + 1
    # Zero-delay retries need not call sleep at all.
    assert [value for value in sleeps if value] == [value for value in expected if value]
