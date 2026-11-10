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
