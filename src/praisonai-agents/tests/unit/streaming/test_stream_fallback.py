"""Regression tests for the streaming -> non-streaming fallback (#4719).

When the streaming transport raises, ``_start_stream_impl`` falls back to
``chat()``. On main the fallback forwarded ``start()``'s raw kwargs, so it
(1) carried ``stream=True`` into the sync path, which refuses to stream,
(2) raised ``TypeError`` for any sampling knob ``chat()`` does not declare
(the desktop passes ``max_tokens`` on every turn), and (3) when the fallback
failed too, the original streaming exception was buried.

These tests drive the real ``start(stream=True)`` -> ``_start_stream_impl``
path with the OpenAI transport stubbed to raise, and assert the observable
effect of the fallback -- not the shape of the code.
"""

import functools
import inspect
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from praisonaiagents import Agent


STREAMING_ERROR = "context too long"


def _completion(text: str):
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content=text, tool_calls=None),
                finish_reason="stop",
            )
        ],
        usage=None,
    )


@pytest.fixture
def agent(monkeypatch):
    """An OpenAI-path agent whose streaming transport always raises."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    agent = Agent(name="fallback-agent", instructions="test", llm="gpt-4o-mini")

    fake_client = MagicMock()
    fake_client.build_messages.return_value = (
        [{"role": "user", "content": "x"}],
        "x",
    )
    # The streaming transport: the sync client's streamed create() dies.
    fake_client.sync_client.chat.completions.create.side_effect = RuntimeError(
        STREAMING_ERROR
    )
    # The non-streaming path chat() ends up on (unified OpenAI adapter).
    fake_client.achat_completion_with_tools = AsyncMock(
        return_value=_completion("ok")
    )
    agent._Agent__openai_client = fake_client
    return agent


def _record_chat_calls(agent, result="ok", raise_with=None):
    """Replace ``agent.chat`` with a recorder that keeps chat()'s signature.

    ``functools.wraps`` exposes the real signature through ``__wrapped__`` so
    the code under test sees exactly what the real ``chat()`` accepts, while
    the recorder itself takes ``**kwargs`` so anything forwarded is captured
    rather than exploding inside the stub.
    """
    calls = []

    @functools.wraps(agent.chat)
    def recording_chat(prompt, **kwargs):
        calls.append(kwargs)
        if raise_with is not None:
            raise raise_with
        return result

    agent.chat = recording_chat
    return calls


class TestStreamFallbackKwargs:
    def test_fallback_reaches_sync_path_with_only_accepted_kwargs(self, agent):
        calls = _record_chat_calls(agent)

        chunks = list(agent.start("x", stream=True, max_tokens=5))

        assert "".join(chunks).strip() == "ok"
        assert len(calls) == 1, "the fallback must run chat() exactly once"
        received = calls[0]
        # (1) the sync path must never be asked to stream
        assert received.get("stream") is False
        # (2) sampling knobs chat() does not declare must be filtered out
        assert "max_tokens" not in received
        accepted = set(inspect.signature(Agent.chat).parameters) - {"self", "prompt"}
        assert set(received) <= accepted, (
            f"fallback forwarded kwargs chat() cannot accept: {set(received) - accepted}"
        )
        # The sync transport was the one actually reached (the streaming
        # transport raised first).
        agent._Agent__openai_client.sync_client.chat.completions.create.assert_called_once()

    def test_fallback_with_real_chat_survives_max_tokens(self, agent):
        # No stub on chat(): the desktop's `max_tokens` must not raise
        # TypeError and the fallback must produce the non-streamed answer.
        chunks = list(agent.start("x", stream=True, max_tokens=5))

        assert "".join(chunks).strip() == "ok"
        agent._Agent__openai_client.achat_completion_with_tools.assert_awaited()
        awaited_kwargs = agent._Agent__openai_client.achat_completion_with_tools.await_args.kwargs
        assert awaited_kwargs.get("stream") is not True


class TestStreamFallbackExceptionChaining:
    def test_fallback_failure_surfaces_original_streaming_error(self, agent):
        calls = _record_chat_calls(agent, raise_with=ValueError("fallback exploded"))

        with pytest.raises(ValueError, match="fallback exploded") as exc_info:
            list(agent.start("x", stream=True, max_tokens=5))

        # (3) the original streaming failure is the explicit cause
        cause = exc_info.value.__cause__
        assert isinstance(cause, RuntimeError)
        assert STREAMING_ERROR in str(cause)
        # and the fallback was not retried a second time on the way out
        assert len(calls) == 1
