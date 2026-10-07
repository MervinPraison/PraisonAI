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


def test_recipe_adapter_bridges_async_callback_on_running_loop(monkeypatch):
    """Production bots schedule a coroutine from the stream callback via
    ``asyncio.get_running_loop().create_task(...)``. The recipe runs on a worker
    thread, so events must be marshalled back onto the loop thread or that call
    raises ``RuntimeError`` and every draft edit is silently dropped. This pins
    the real bot contract that a plain sync-list callback cannot exercise."""
    adapter = RecipeBotAdapter("demo")
    monkeypatch.setattr(adapter, "_recipe_module", lambda: _fake_recipe_module())

    delivered = []
    errors = []

    async def _drain():
        async def _async_handler(event):
            delivered.append(event.type)

        def _bridge(event):
            # Exactly what praisonai_bot._session does on the hot path.
            try:
                asyncio.get_running_loop().create_task(_async_handler(event))
            except RuntimeError as exc:  # no loop on this thread → bug
                errors.append(exc)

        adapter.stream_emitter.add_callback(_bridge)
        final = await adapter.astart("world", stream=True)
        # Let the scheduled coroutine tasks run.
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        return final

    final = asyncio.run(_drain())

    assert final == "Hello world"
    assert errors == [], "events were emitted off the loop thread (draft edits lost)"
    assert StreamEventType.DELTA_TEXT in delivered
    assert StreamEventType.STREAM_END in delivered


def test_recipe_adapter_forwards_cancel_token_to_runtime(monkeypatch):
    """A cancel token the runtime understands must be forwarded so the recipe can
    stop cooperatively, not just our local iteration."""
    seen = {}

    class _Recipe:
        @staticmethod
        def run_stream(name, input=None, config=None, cancel_token=None):
            seen["cancel_token"] = cancel_token
            yield _RecEvent("output", {"output": {"reply": "ok"}})
            yield _RecEvent("completed", {"status": "success"})

    token = object()
    adapter = RecipeBotAdapter("demo")
    monkeypatch.setattr(adapter, "_recipe_module", lambda: _Recipe())

    final = asyncio.run(adapter.astart("hi", stream=True, cancel_token=token))

    assert final == "ok"
    assert seen["cancel_token"] is token


def test_recipe_adapter_stops_iterating_when_cancelled(monkeypatch):
    """When the runtime cannot take a cancel token, a cancelled token must still
    stop the adapter from processing further events after cancellation."""
    emitted_after_cancel = []

    class _Token:
        def __init__(self):
            self.cancelled = False

        def is_cancelled(self):
            return self.cancelled

    token = _Token()

    class _Recipe:
        @staticmethod
        def run_stream(name, input=None, config=None):
            yield _RecEvent("progress", {"step": "s1", "message": "first"})
            token.cancelled = True  # turn is cancelled mid-stream
            yield _RecEvent("output", {"output": {"reply": "should-not-stream"}})

    adapter = RecipeBotAdapter("demo")
    monkeypatch.setattr(adapter, "_recipe_module", lambda: _Recipe())

    def _record(event):
        if event.type == StreamEventType.DELTA_TEXT:
            emitted_after_cancel.append(event.content)

    adapter.stream_emitter.add_callback(_record)

    asyncio.run(adapter.astart("hi", stream=True, cancel_token=token))

    assert "should-not-stream" not in emitted_after_cancel


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
