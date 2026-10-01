"""Recipe gateway failures use the core failure reply contract."""

import asyncio

from praisonaiagents.gateway.adapters.recipe_adapter import RecipeBotAdapter
from praisonaiagents.streaming import StreamEventType


def test_recipe_adapter_does_not_return_raw_exception(monkeypatch):
    adapter = RecipeBotAdapter("demo")

    def fail():
        raise RuntimeError("private-recipe-detail")

    monkeypatch.setattr(adapter, "_recipe_module", fail)

    reply = adapter.chat("hello")

    assert reply == "I couldn't complete that due to an unexpected error. Please resend."
    assert "private-recipe-detail" not in reply


class _RecEvent:
    def __init__(self, event_type, data):
        self.event_type = event_type
        self.data = data


def _fake_recipe_module(reply="Hello world"):
    class _Recipe:
        @staticmethod
        def run_stream(name, input=None, config=None):
            yield _RecEvent("progress", {"step": "executing", "message": "Executing recipe"})
            yield _RecEvent("output", {"output": {"reply": reply}})
            yield _RecEvent("completed", {"status": "success"})

        @staticmethod
        def run(name, input=None, config=None):
            class _Result:
                ok = True
                output = {"reply": reply}
                error = None

            return _Result()

    return _Recipe()


def test_recipe_adapter_streams_into_emitter(monkeypatch):
    adapter = RecipeBotAdapter("demo")
    monkeypatch.setattr(adapter, "_recipe_module", lambda: _fake_recipe_module())

    events = []
    adapter.stream_emitter.add_callback(events.append)

    final = asyncio.run(adapter.astart("world", stream=True))

    assert final == "Hello world"
    types_seen = [e.type for e in events]
    assert StreamEventType.DELTA_TEXT in types_seen
    assert StreamEventType.STREAM_END in types_seen
    assert StreamEventType.TOOL_PROGRESS in types_seen


def test_recipe_adapter_achat_without_listeners_returns_text(monkeypatch):
    adapter = RecipeBotAdapter("demo")
    monkeypatch.setattr(adapter, "_recipe_module", lambda: _fake_recipe_module("done"))

    final = asyncio.run(adapter.achat("x"))

    assert final == "done"


def test_recipe_adapter_astart_degrades_on_error(monkeypatch):
    adapter = RecipeBotAdapter("demo")

    class _Recipe:
        @staticmethod
        def run_stream(name, input=None, config=None):
            yield _RecEvent("error", {"message": "private-recipe-detail"})

    monkeypatch.setattr(adapter, "_recipe_module", lambda: _Recipe())

    reply = asyncio.run(adapter.astart("hello", stream=True))

    assert reply == "I couldn't complete that due to an unexpected error. Please resend."
    assert "private-recipe-detail" not in reply
