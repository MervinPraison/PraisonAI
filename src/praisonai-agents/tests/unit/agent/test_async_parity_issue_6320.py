"""Regression tests for #6320 — async path parity (argument casting, cancel_token)."""
import asyncio
import threading

import pytest

from praisonaiagents import Agent


@pytest.fixture(autouse=True)
def _key(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")


def repeat(text: str, n: int, loud: bool = False) -> str:
    return (text * n).upper() if loud else text * n


def test_async_tool_casts_arguments_like_sync():
    a = Agent(name="a", instructions="x", llm="gpt-4o-mini", tools=[repeat])
    args = {"text": "ab", "N": "3", "loud": "false"}
    assert a.execute_tool("repeat", dict(args)) == "ababab"
    assert asyncio.run(a.execute_tool_async("repeat", dict(args))) == "ababab"


def test_achat_forwards_cancel_token_to_dispatcher():
    seen = {}

    class D:
        model = "gpt-4o-mini"

        def chat_completion(self, **kw):
            seen["sync"] = kw.get("cancel_token")
            return "ok"

        async def achat_completion(self, **kw):
            seen["async"] = kw.get("cancel_token")
            return "ok"

    a = Agent(name="b", instructions="x", llm="gpt-4o-mini")
    a._unified_dispatcher = D()
    asyncio.run(a.achat("hi", cancel_token=threading.Event()))
    assert seen.get("async") is not None


def test_async_recovery_backoff_stops_on_cancel_token():
    import time
    from praisonaiagents.agent.chat_mixin import _abackoff

    a = Agent(name="c", instructions="x", llm="gpt-4o-mini")
    tok = threading.Event()
    tok.set()
    t0 = time.monotonic()
    assert asyncio.run(_abackoff(a, 30.0, tok)) is False
    assert time.monotonic() - t0 < 1.0
    assert asyncio.run(_abackoff(a, 0.01, None)) is True


def lookup(record_id: int) -> int:
    return record_id


def test_cast_large_int_string_not_rounded():
    a = Agent(name="d", instructions="x", llm="gpt-4o-mini", tools=[lookup])
    big = "9007199254740993"
    assert a._cast_arguments(lookup, {"record_id": big}) == {"record_id": 9007199254740993}
    assert a._cast_arguments(lookup, {"record_id": "3.0"}) == {"record_id": 3}
    assert asyncio.run(a.execute_tool_async("lookup", {"record_id": big})) == 9007199254740993


def test_cast_large_int_string_in_optional_not_rounded():
    from typing import Optional
    from praisonaiagents.agent.tool_execution import _coerce_value
    assert _coerce_value("9007199254740993", Optional[int]) == 9007199254740993
    assert _coerce_value("1" * 400, Optional[int]) == int("1" * 400)  # beyond float range
    assert _coerce_value("3.0", Optional[int]) == 3
    assert _coerce_value("1.5", Optional[int]) == "1.5"
