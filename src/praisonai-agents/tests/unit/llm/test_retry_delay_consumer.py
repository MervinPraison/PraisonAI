"""The retry loop must consume complete numeric hints like the shared parser."""

import pytest

from praisonaiagents.llm.llm import LLM


@pytest.mark.parametrize("template", [
    'rate limit: retry after {} seconds',
    'rate limit: try again in {}',
    'rate limit: Retry-After: {}',
    'rate limit: "retryDelay": "{}s"',
    'rate limit: retryDelay: {}s',
])
@pytest.mark.parametrize("token,expected", [
    (".5", .5), ("1e2", 100), ("0", 0), ("999", 300),
    ("-.5", 60), ("-5", 60), ("1e309", 60), ("1.2.3", 60),
])
def test_retry_decision_uses_complete_numeric_hint(template, token, expected):
    llm = LLM(model="fake")
    assert llm._parse_retry_delay(template.format(token)) == expected
    decision = llm.resolve_failover_decision(
        Exception(template.format(token)),
        {"attempt": 1, "max_retries": 3, "side_effecting": False},
    )
    assert decision.reason == "rate_limit"
    # The existing decision applies its exponential floor to a zero hint.
    assert decision.backoff_ms == int((expected or 1) * 1000)


def test_retry_parser_keeps_configured_cap_and_default():
    from types import SimpleNamespace

    llm = LLM(model="fake")
    llm._rate_limiter = SimpleNamespace(max_retry_delay=12)
    llm._retry_delay = 7
    assert llm._parse_retry_delay('try again in 1e2') == 12
    assert llm._parse_retry_delay('no retry hint') == 7


def test_sync_retry_waits_for_fractional_hint():
    from types import SimpleNamespace

    waits = []
    llm = LLM(model="fake")
    llm._max_retries = 1
    llm._rate_limiter = SimpleNamespace(
        acquire=lambda: None, wait_for_retry=waits.append,
    )
    calls = 0

    def completion(**kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise Exception('rate limit: retry after .5 seconds')
        return 'done'

    assert llm._call_with_retry(completion) == 'done'
    assert waits == [.5]
    assert calls == 2


@pytest.mark.asyncio
async def test_async_retry_waits_for_exponent_hint():
    from types import SimpleNamespace

    waits = []

    async def acquire():
        pass

    async def wait(delay):
        waits.append(delay)

    llm = LLM(model="fake")
    llm._max_retries = 1
    llm._rate_limiter = SimpleNamespace(acquire_async=acquire, wait_for_retry_async=wait)
    calls = 0

    async def completion(**kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise Exception('rate limit: try again in 1e2')
        return 'done'

    assert await llm._call_with_retry_async(completion) == 'done'
    assert waits == [100]
    assert calls == 2
