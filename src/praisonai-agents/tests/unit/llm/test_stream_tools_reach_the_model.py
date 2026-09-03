"""Tool calls must survive both paths of get_response_stream.

Two defects made streaming tool calls do nothing at all, and they compounded:

1. `_create_tool_message` was called from the streaming tool loop
   (llm.py, twice) and never defined anywhere in the package. The first tool
   result raised AttributeError. The broad `except Exception` around that loop
   swallowed it, logged a warning, set `use_streaming = False`, and fell
   through to the non-streaming branch.

2. That non-streaming branch read `message.content` and nothing else. It sent
   `tools=` in the request, so the model answered with `tool_calls` and empty
   content -- and every call was discarded. The tool never ran, nothing was
   yielded, and no error surfaced.

Net effect: on a turn that needed a tool, the user got an empty answer. The
second branch is not an edge case -- Anthropic, Gemini and Ollama all report
False from `_supports_streaming_tools()`, so they take it on every tools turn.

The two tests that covered the streaming loop assigned `_create_tool_message`
onto the instance themselves, so they passed against a method production did
not have. These tests never patch it.
"""
import os
import types

import pytest

os.environ.setdefault("OPENAI_API_KEY", "sk-test-not-real")

from praisonaiagents.llm.llm import LLM


def _tool_call(name="get_weather", args='{"city":"Paris"}', call_id="call_1"):
    return types.SimpleNamespace(
        index=0, id=call_id, type="function",
        function=types.SimpleNamespace(name=name, arguments=args))


def get_weather(city: str) -> str:
    return f"sunny in {city}"


class TestCreateToolMessageExists:
    """Guards the premise: production must own this method, not the tests."""

    def test_the_method_is_defined_on_the_class(self):
        assert hasattr(LLM, "_create_tool_message"), (
            "_create_tool_message is called by the streaming tool loop; if only "
            "tests define it, every streaming tool turn raises AttributeError"
        )

    def test_it_builds_a_standard_tool_message(self):
        llm = LLM(model="gpt-4o-mini")
        msg = llm._create_tool_message("get_weather", "sunny", "call_1", False)
        assert msg["role"] == "tool"
        assert msg["tool_call_id"] == "call_1"
        assert "sunny" in msg["content"]

    def test_an_error_result_is_reported_as_an_error(self):
        llm = LLM(model="gpt-4o-mini")
        msg = llm._create_tool_message("f", {"error": "boom"}, "call_1", False)
        assert "boom" in msg["content"]

    def test_an_empty_result_is_named_rather_than_dropped(self):
        llm = LLM(model="gpt-4o-mini")
        msg = llm._create_tool_message("f", None, "call_1", False)
        assert msg["content"], "an empty tool result must still say something"


class TestNonStreamingFallbackRunsTools:
    """Anthropic, Gemini and Ollama take this branch on every tools turn."""

    def _llm_with_two_turns(self, model="anthropic/claude-sonnet-4-20250514"):
        llm = LLM(model=model)
        state = {"turns": 0, "ran": 0}

        def fake_completion(**kwargs):
            state["turns"] += 1
            if state["turns"] == 1:
                message = types.SimpleNamespace(content=None, tool_calls=[_tool_call()])
            else:
                message = types.SimpleNamespace(content="It is sunny in Paris.",
                                                tool_calls=None)
            return types.SimpleNamespace(
                choices=[types.SimpleNamespace(message=message, finish_reason="stop")])

        def execute(name, args, *a, **kw):
            state["ran"] += 1
            return get_weather(**args)

        llm._completion_with_retry = fake_completion
        return llm, state, execute

    def test_the_provider_really_takes_this_branch(self):
        for model in ("anthropic/claude-sonnet-4-20250514",
                      "gemini/gemini-2.0-flash", "ollama/llama3.2"):
            assert LLM(model=model)._supports_streaming_tools() is False, model

    def test_the_tool_actually_runs(self):
        llm, state, execute = self._llm_with_two_turns()
        list(llm.get_response_stream(prompt="weather?", system_prompt="x",
                                     tools=[get_weather], execute_tool_fn=execute))
        assert state["ran"] == 1, "the tool call was discarded"

    def test_the_answer_reaches_the_caller(self):
        llm, state, execute = self._llm_with_two_turns()
        out = list(llm.get_response_stream(prompt="weather?", system_prompt="x",
                                           tools=[get_weather], execute_tool_fn=execute))
        assert "".join(out).strip(), "a tool turn produced an empty stream"

    def test_it_asks_the_model_again_with_the_result(self):
        llm, state, execute = self._llm_with_two_turns()
        list(llm.get_response_stream(prompt="weather?", system_prompt="x",
                                     tools=[get_weather], execute_tool_fn=execute))
        assert state["turns"] == 2, "the tool result was never sent back"

    def test_a_turn_with_no_tool_calls_still_yields_its_prose(self):
        llm = LLM(model="anthropic/claude-sonnet-4-20250514")
        message = types.SimpleNamespace(content="plain answer", tool_calls=None)
        llm._completion_with_retry = lambda **kw: types.SimpleNamespace(
            choices=[types.SimpleNamespace(message=message, finish_reason="stop")])
        out = list(llm.get_response_stream(prompt="hi", system_prompt="x",
                                           tools=[get_weather],
                                           execute_tool_fn=lambda *a, **k: None))
        assert "".join(out) == "plain answer"

    def test_a_failing_tool_is_reported_not_raised(self):
        """A broken tool must reach the model as an error, not abort the run."""
        llm, state, _ = self._llm_with_two_turns()

        def boom(name, args, *a, **kw):
            raise RuntimeError("tool exploded")

        out = list(llm.get_response_stream(prompt="weather?", system_prompt="x",
                                           tools=[get_weather], execute_tool_fn=boom))
        assert state["turns"] == 2, "a failing tool aborted the turn"
        assert "".join(out).strip()

    def test_it_stops_at_max_tool_calls_per_turn(self):
        """The fallback must honour the same per-turn guardrail as the other loops."""
        llm = LLM(model="anthropic/claude-sonnet-4-20250514")
        state = {"ran": 0}

        def always_calls(**kwargs):
            message = types.SimpleNamespace(content=None, tool_calls=[_tool_call()])
            return types.SimpleNamespace(
                choices=[types.SimpleNamespace(message=message, finish_reason="tool_calls")])

        def execute(name, args, *a, **kw):
            state["ran"] += 1
            return get_weather(**args)

        llm._completion_with_retry = always_calls
        list(llm.get_response_stream(prompt="weather?", system_prompt="x",
                                     tools=[get_weather], execute_tool_fn=execute,
                                     max_tool_calls_per_turn=3))
        assert state["ran"] == 3, (
            "the fallback ran tools past max_tool_calls_per_turn")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
