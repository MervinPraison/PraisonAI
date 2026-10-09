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


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-v"]))
