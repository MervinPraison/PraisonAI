"""Headerless rate limits use existing jitter unless the caller selected a delay."""
import asyncio
from unittest.mock import AsyncMock

import pytest

from praisonaiagents.llm.llm import LLM


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
        with pytest.raises(RateLimited):
            asyncio.run(llm._call_with_retry_async(AsyncMock(side_effect=error)))
    else:
        monkeypatch.setattr("praisonaiagents.llm.llm.time.sleep", sleeps.append)
        def fail():
            raise error
        with pytest.raises(RateLimited):
            llm._call_with_retry(fail)
    # Zero-delay retries need not call sleep at all.
    assert [value for value in sleeps if value] == [value for value in expected if value]
