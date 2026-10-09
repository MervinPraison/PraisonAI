"""Regression test for issue #5737.

`Agent.chat(prompt, stream=True)` against the sync OpenAI adapter used to let
the adapter's ``ValueError("Streaming is not supported in sync OpenAIAdapter")``
bubble up to ``chat()``'s outer handler, which logged an error and returned
``None``. Callers iterating the result got no tokens and no typed error.

The fix makes an explicit ``stream=True`` transparently fall back to the
non-streaming path inside ``_chat_completion`` (mirroring the existing
``stream=None`` auto-detect behaviour) so ``chat()`` still returns text.

This test drives ``_chat_completion`` directly with a mocked
``_chat_completion_with_retry`` so no live LLM is needed.
"""

import types

import pytest

from praisonaiagents.agent.chat_mixin import ChatMixin


class _Stub(ChatMixin):
    """Minimal ChatMixin host that stubs out everything _chat_completion needs."""

    def __init__(self):
        self.name = "stub"
        self.llm = "gpt-4o-mini"
        self.verbose = False
        self._last_stop_reason = "completed"
        self._max_budget = None
        self._on_budget_exceeded = "warn"
        self._total_cost = 0.0
        self._total_tokens_in = 0
        self._total_tokens_out = 0
        self._llm_call_count = 0
        self.calls = []

        import threading
        self._cost_lock = threading.Lock()

        # Hook runner that reports no registered hooks.
        class _Registry:
            def has_hooks(self, *_a, **_k):
                return False

        class _HookRunner:
            registry = _Registry()

            def execute_sync(self, *_a, **_k):
                return []

            def is_blocked(self, *_a, **_k):
                return False

        self._hook_runner = _HookRunner()

    # --- stub out the heavy collaborators _chat_completion calls ---
    def _compute_context_budget_and_route(self, messages, tools, system_prompt):
        return "passthrough", messages

    def _apply_context_compaction(self, messages, hook_event):
        return None

    def _format_tools_for_completion(self, tools):
        return tools

    def _apply_before_tool_definitions_hook(self, formatted_tools):
        return formatted_tools

    def _extract_llm_response_content(self, response):
        return response

    def _calculate_llm_cost(self, *_a, **_k):
        return 0.0


def _make_retry(behaviour):
    """Build a _chat_completion_with_retry that records stream= and acts."""
    def _retry(self, *, stream=None, **kwargs):
        self.calls.append(stream)
        return behaviour(stream)
    return _retry


def test_explicit_stream_true_falls_back_to_nonstreaming():
    """stream=True on a sync adapter returns text instead of None."""
    stub = _Stub()

    def behaviour(stream):
        if stream:
            raise ValueError(
                "Streaming is not supported in sync OpenAIAdapter. "
                "Use achat_completion() for streaming support."
            )
        return "hello world"

    stub._chat_completion_with_retry = types.MethodType(_make_retry(behaviour), stub)

    result = stub._chat_completion([{"role": "user", "content": "hi"}], stream=True)

    assert result == "hello world"
    # First call attempted streaming, second call fell back to non-streaming.
    assert stub.calls == [True, False]


def test_explicit_stream_true_never_returns_none_on_adapter_valueerror():
    stub = _Stub()

    def behaviour(stream):
        if stream:
            raise ValueError("Streaming is not supported in sync OpenAIAdapter.")
        return "non-empty"

    stub._chat_completion_with_retry = types.MethodType(_make_retry(behaviour), stub)

    result = stub._chat_completion([{"role": "user", "content": "hi"}], stream=True)

    assert result is not None
    assert result == "non-empty"


def test_unrelated_valueerror_is_not_swallowed():
    """Only the streaming-unsupported ValueError triggers the fallback.

    An unrelated ValueError must still surface (as the normal LLMError the
    error handler raises), never be retried as non-streaming, and never be
    swallowed into None.
    """
    from praisonaiagents.errors import LLMError

    stub = _Stub()

    def behaviour(stream):
        raise ValueError("some other failure")

    stub._chat_completion_with_retry = types.MethodType(_make_retry(behaviour), stub)

    with pytest.raises(LLMError, match="some other failure"):
        stub._chat_completion([{"role": "user", "content": "hi"}], stream=True)

    # Only the streaming attempt happened; no non-streaming retry was made.
    assert stub.calls == [True]


def test_public_agent_chat_stream_true_returns_text_via_real_extraction():
    """End-to-end public path: ``Agent.chat(stream=True)`` returns text.

    The unit tests above drive ``_chat_completion`` with a mocked retry helper
    that returns a bare string, so they never exercise ``chat()``'s real
    ``response.choices[0].message.content`` extraction (greptile finding on
    PR #5739). This test builds a real ``Agent`` and mocks only the lowest
    dispatch seam (``_execute_unified_chat_completion``) so the whole public
    return path runs: it raises the sync-adapter ``ValueError`` on the explicit
    streaming attempt and returns a realistic completion object (with
    ``choices[0].message.content``) on the non-streaming fallback. A broken
    public return would surface here as ``None`` or the wrong text.
    """
    import os
    import types

    os.environ.setdefault("OPENAI_API_KEY", "sk-test-key-for-reproduction")

    from praisonaiagents import Agent

    agent = Agent(instructions="Reply with exactly the requested text")

    completion = types.SimpleNamespace(
        choices=[
            types.SimpleNamespace(
                message=types.SimpleNamespace(
                    content="fallback text", tool_calls=None
                ),
                finish_reason="stop",
            )
        ],
        usage=types.SimpleNamespace(prompt_tokens=1, completion_tokens=2),
    )

    seen_streams = []

    def fake_execute(self, messages, temperature=None, tools=None, stream=None,
                     *args, **kwargs):
        seen_streams.append(stream)
        if stream:
            raise ValueError(
                "Streaming is not supported in sync OpenAIAdapter. "
                "Use achat_completion() for streaming support."
            )
        return completion

    agent._execute_unified_chat_completion = types.MethodType(fake_execute, agent)

    result = agent.chat("hi", stream=True)

    assert result is not None
    assert result == "fallback text"
    # Explicit streaming attempt happened, then non-streaming fallback.
    assert True in seen_streams
    assert False in seen_streams


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-v"]))
