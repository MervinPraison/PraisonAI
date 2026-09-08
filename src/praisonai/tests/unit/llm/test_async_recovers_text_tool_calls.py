"""The async path lost tool calls the sync path recovers.

Small local models routinely answer with the tool call as JSON *content*
instead of populating `tool_calls` -- especially after a repair prompt.
`get_response` has recovered those since the adapter seam landed.
`get_response_async` did not, so the same agent silently stopped calling tools
the moment the caller awaited instead of called.
"""

import asyncio
import types

import pytest

from praisonaiagents.llm.llm import LLM


def get_weather(city: str) -> str:
    """Get the weather for a city.

    Args:
        city: the city
    """
    return f"{city}: 21C sunny"


TEXT_TOOL_CALL = '{"name": "get_weather", "arguments": {"city": "Paris"}}'


def _response(content, tool_calls=None):
    """A litellm-shaped response that supports both attribute and item access."""
    class M(dict):
        def __init__(self, **kw):
            super().__init__(**kw)
            self.__dict__.update(kw)
    msg = M(content=content, tool_calls=tool_calls)
    choice = M(message=msg, finish_reason="stop")
    return M(choices=[choice])


@pytest.fixture
def llm(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "x")
    return LLM(model="ollama/qwen3:0.6b", base_url="http://127.0.0.1:11434")


class TestAsyncRecoversTextEmittedToolCalls:
    def test_async_recovers_a_tool_call_emitted_as_text(self, llm):
        """This is the regression: async saw prose, sync saw a tool call."""
        calls = []

        async def fake(**kwargs):
            # Second turn: answer normally so the loop terminates.
            if any(m.get("role") == "user" and "Tool execution" in str(m.get("content", ""))
                   for m in kwargs.get("messages", [])):
                return _response("It is sunny in Paris.")
            return _response(TEXT_TOOL_CALL)

        llm._acompletion_with_retry = fake

        def execute(name, args, *a, **kw):
            calls.append((name, args))
            return get_weather(**args)

        asyncio.run(llm.get_response_async(
            prompt="weather in Paris?", tools=[get_weather],
            execute_tool_fn=execute, temperature=0, verbose=False, stream=False))

        assert calls == [("get_weather", {"city": "Paris"})], (
            f"async did not recover the tool call from text: {calls!r}"
        )

    def test_a_hosted_provider_recovers_nothing(self, monkeypatch):
        """The guard is adapter-driven, so hosted providers are unaffected.

        DefaultAdapter returns None, so a hosted model that happens to emit
        JSON prose keeps it as prose rather than having it run as a tool call.
        """
        monkeypatch.setenv("OPENAI_API_KEY", "x")
        formatted = [{"type": "function", "function": {"name": "get_weather"}}]
        assert LLM(model="gpt-4o")._provider_adapter.recover_tool_calls_from_text(
            TEXT_TOOL_CALL, formatted) is None
        assert LLM(model="claude-3-5-sonnet-latest")._provider_adapter.recover_tool_calls_from_text(
            TEXT_TOOL_CALL, formatted) is None
        # ...while the local one does recover, which is what makes the
        # async fix above reachable at all.
        assert LLM(model="ollama/qwen3:0.6b")._provider_adapter.recover_tool_calls_from_text(
            TEXT_TOOL_CALL, formatted) is not None

    def test_native_tool_calls_still_take_precedence(self, llm):
        """Recovery must not override a call the provider surfaced properly."""
        calls = []

        native = [{"id": "c1", "type": "function",
                   "function": {"name": "get_weather",
                                "arguments": '{"city": "Berlin"}'}}]

        async def fake(**kwargs):
            if any("Tool execution" in str(m.get("content", ""))
                   for m in kwargs.get("messages", [])):
                return _response("Done.")
            return _response(TEXT_TOOL_CALL, tool_calls=native)

        llm._acompletion_with_retry = fake

        def execute(name, args, *a, **kw):
            calls.append(args.get("city"))
            return "ok"

        asyncio.run(llm.get_response_async(
            prompt="weather?", tools=[get_weather], execute_tool_fn=execute,
            temperature=0, verbose=False, stream=False))
        assert calls == ["Berlin"], f"the native call must win, got {calls!r}"
