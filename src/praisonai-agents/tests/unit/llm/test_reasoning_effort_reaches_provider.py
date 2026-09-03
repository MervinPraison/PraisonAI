"""reasoning_effort must reach the provider, not just the kwargs dict.

The desktop's Settings -> Models -> "Reasoning effort" control is persisted,
forwarded into `agent.start(**kwargs)`, and was then discarded: neither
streaming branch of `_start_stream_impl` read it. `grep -c reasoning_effort
chat_mixin.py` returned 0. Every level from minimal to high produced a
byte-identical provider request, with no error and no warning, while the UI
promised "Maps to each backend's native knob".

The guard that was supposed to catch this asserts against a *stub agent* that
records the kwargs it was handed, so it passed while the real Agent dropped
the value. These tests assert on what the transport actually receives.

resolve_reasoning_params returns {} for "off", for an unset level, and for a
model with no reasoning control, so wiring it through stays a no-op except
where it means something.
"""
import os
import types

import pytest

os.environ.setdefault("OPENAI_API_KEY", "sk-test-not-real")

from praisonaiagents import Agent
from praisonaiagents.llm import get_openai_client


def _request_for(model, **start_kwargs):
    """Drive a real Agent, faking only the transport, and return the request."""
    seen = {}
    real = get_openai_client(api_key="sk-test-not-real")

    class _Completions:
        def create(self, **kw):
            seen.update(kw)
            delta = types.SimpleNamespace(content="ok", tool_calls=None)
            return iter([types.SimpleNamespace(
                choices=[types.SimpleNamespace(delta=delta, finish_reason="stop")])])

    class _Proxy:
        sync_client = types.SimpleNamespace(
            chat=types.SimpleNamespace(completions=_Completions()))

        def __getattr__(self, name):
            return getattr(real, name)

    agent = Agent(name="t", instructions="x", llm=model)
    agent._Agent__openai_client = _Proxy()
    list(agent.start("hi", stream=True, **start_kwargs))
    return seen


class TestReasoningEffortReachesTheProvider:

    def test_a_reasoning_model_gets_the_native_knob(self):
        req = _request_for("o4-mini", reasoning_effort="high")
        assert req.get("reasoning_effort") == "high", (
            "reasoning_effort never reached the provider request"
        )

    def test_off_sends_nothing(self):
        req = _request_for("o4-mini", reasoning_effort="off")
        assert "reasoning_effort" not in req
        assert "thinking" not in req

    def test_an_unset_level_sends_nothing(self):
        req = _request_for("o4-mini")
        assert "reasoning_effort" not in req

    def test_a_model_without_a_reasoning_knob_is_untouched(self):
        """Wiring this through must not change ordinary chat models."""
        req = _request_for("gpt-4o-mini", reasoning_effort="high")
        assert "reasoning_effort" not in req
        assert "thinking" not in req

    def test_extended_thinking_budget_goes_through_extra_body(self):
        """A ``thinking`` budget is not a native OpenAI SDK keyword.

        resolve_reasoning_params emits ``{"thinking": ...}`` for an
        extended-thinking-named model. On this direct path the request is
        handed to the raw OpenAI SDK, which rejects unknown top-level kwargs
        with TypeError, so the budget must ride inside ``extra_body`` while
        ``reasoning_effort`` stays top-level.
        """
        req = _request_for("claude-3-7-sonnet", reasoning_effort="high")
        assert "thinking" not in req, (
            "thinking must not be a top-level kwarg; the OpenAI SDK rejects it"
        )
        assert req.get("extra_body", {}).get("thinking") == {
            "type": "enabled", "budget_tokens": 16000,
        }

    def test_native_effort_stays_top_level_not_in_extra_body(self):
        """reasoning_effort is native; it must not be buried in extra_body."""
        req = _request_for("o4-mini", reasoning_effort="high")
        assert req.get("reasoning_effort") == "high"
        assert "reasoning_effort" not in req.get("extra_body", {})

    def test_the_ordinary_request_still_looks_right(self):
        """Guards against the merge clobbering the rest of the payload."""
        req = _request_for("gpt-4o-mini")
        for key in ("model", "messages", "stream"):
            assert key in req, key

    def test_the_agent_attribute_is_used_when_no_kwarg_is_passed(self):
        """Construction-time configuration must work on this path too."""
        seen = {}
        real = get_openai_client(api_key="sk-test-not-real")

        class _Completions:
            def create(self, **kw):
                seen.update(kw)
                delta = types.SimpleNamespace(content="ok", tool_calls=None)
                return iter([types.SimpleNamespace(
                    choices=[types.SimpleNamespace(delta=delta, finish_reason="stop")])])

        class _Proxy:
            sync_client = types.SimpleNamespace(
                chat=types.SimpleNamespace(completions=_Completions()))

            def __getattr__(self, name):
                return getattr(real, name)

        agent = Agent(name="t", instructions="x", llm="o4-mini", reasoning_effort="high")
        agent._Agent__openai_client = _Proxy()
        list(agent.start("hi", stream=True))
        assert seen.get("reasoning_effort") == "high"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
