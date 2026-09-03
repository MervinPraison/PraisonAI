"""Regression tests for the streaming-error fallback (issue #4719).

When a streaming request raises, `_start_stream_impl` falls back to the sync
`self.chat(...)` via `_stream_fallback_chat`. `start()` has already merged
`stream=True` (and knobs like `max_tokens`/`top_p`) into the kwargs it forwards,
so a naive fallback:

  1. reached the sync adapter with `stream=True` ("Streaming is not supported"),
  2. raised `TypeError` for kwargs `chat()` cannot name (e.g. `max_tokens`),
  3. surfaced the fallback's error instead of the real streaming cause.

These tests exercise the fix without a live LLM by driving the private helper
`_stream_fallback_chat` directly.
"""

import types

import pytest

from praisonaiagents.agent.chat_mixin import ChatMixin


class _Stub(ChatMixin):
    """Minimal object exposing ChatMixin's helper + a recording chat()."""

    def __init__(self):
        self.recorded = None

    def chat(self, prompt, temperature=None, tools=None, output_json=None,
             output_pydantic=None, reasoning_steps=False, stream=None,
             task_name=None, task_description=None, task_id=None, config=None,
             force_retrieval=False, skip_retrieval=False, attachments=None,
             tool_choice=None, seed=None, cancel_token=None):
        self.recorded = {
            "prompt": prompt,
            "stream": stream,
            "temperature": temperature,
            "tools": tools,
        }
        return "sync answer"


def test_fallback_strips_stream_and_unknown_kwargs():
    """stream is forced False; kwargs chat() cannot name are dropped."""
    stub = _Stub()
    kwargs = {
        "stream": True,
        "max_tokens": 128,   # not a chat() parameter
        "top_p": 0.9,        # not a chat() parameter
        "temperature": 0.5,  # accepted
        "tools": ["t"],      # accepted
    }

    result = stub._stream_fallback_chat("hello", kwargs, RuntimeError("boom"))

    assert result == "sync answer"
    assert stub.recorded is not None
    assert stub.recorded["prompt"] == "hello"
    assert stub.recorded["stream"] is False, "sync path must not be asked to stream"
    assert stub.recorded["temperature"] == 0.5
    assert stub.recorded["tools"] == ["t"]


def test_fallback_never_asks_sync_path_to_stream():
    stub = _Stub()
    kwargs = {"stream": True, "max_tokens": 64, "temperature": 0.2}

    stub._stream_fallback_chat("hi", kwargs, RuntimeError("boom"))

    assert stub.recorded is not None
    assert stub.recorded["stream"] is False
    assert stub.recorded["temperature"] == 0.2


def test_original_streaming_exception_is_surfaced_when_fallback_fails():
    """When the fallback also fails, the ORIGINAL cause is the chained root."""
    original = ValueError("context length exceeded")

    def failing_chat(self, prompt, **kwargs):
        raise RuntimeError("Streaming is not supported in sync OpenAIAdapter")

    stub = _Stub()
    stub.chat = types.MethodType(failing_chat, stub)

    with pytest.raises(RuntimeError) as exc_info:
        stub._stream_fallback_chat("hi", {"stream": True}, original)

    # The fallback failure is raised, but chained from the original streaming
    # cause so the real reason (context length) is not lost.
    assert exc_info.value.__cause__ is original
    # And the outer handler is told the fallback was already exhausted so it
    # does not run chat() a second time.
    assert getattr(exc_info.value, "_praisonai_stream_fallback_exhausted", False)


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-v"]))
