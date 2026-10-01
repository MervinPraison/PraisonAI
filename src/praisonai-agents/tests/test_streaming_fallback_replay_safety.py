"""Regression tests for streaming-fallback replay safety (issue #5445).

Switching response mode (streaming -> non-streaming) is still a *provider
replay*. The retry driver already surfaces a post-dispatch failure (read
timeout, connection reset mid-response) on a side-effecting tool turn rather
than replaying it, because a tool call may already have run server-side
(#3860). But the outer fallbacks used to catch that surfaced error and reissue
the same request with ``stream=False``, bypassing the decision.

These tests drive the private ``ChatMixin._stream_fallback_chat`` helper and the
``is_replay_unsafe_chain`` classifier directly, with no live LLM or provider.
"""

import types

import pytest

from praisonaiagents.agent.chat_mixin import ChatMixin
from praisonaiagents.llm.error_classifier import (
    is_replay_unsafe,
    is_replay_unsafe_chain,
)


class _ReadTimeout(Exception):
    """Stand-in whose class name matches the replay-unsafe signal."""


class _ConnectTimeout(Exception):
    """Stand-in whose class name matches a pre-dispatch (replay-safe) signal."""


class _RecordingHost(ChatMixin):
    """Minimal ChatMixin host with a recording chat() and optional tools."""

    def __init__(self, tools=None):
        self.tools = tools
        self.calls = []

    def chat(self, prompt, temperature=None, tools=None, output_json=None,
             output_pydantic=None, reasoning_steps=False, stream=None,
             task_name=None, task_description=None, task_id=None, config=None,
             force_retrieval=False, skip_retrieval=False, attachments=None,
             tool_choice=None, seed=None, cancel_token=None):
        self.calls.append({"prompt": prompt, "stream": stream, "tools": tools})
        return "sync answer"


# --- classifier chain behaviour -------------------------------------------

def test_wrapped_read_timeout_is_unsafe_in_chain():
    rt = _ReadTimeout("read timed out")
    wrapped = Exception("Stream iteration failed with recoverable error")
    wrapped.__cause__ = rt
    # The top-level wrapper alone does not look unsafe...
    assert is_replay_unsafe(wrapped) is False
    # ...but the chain walk finds the read timeout underneath.
    assert is_replay_unsafe_chain(wrapped) is True


def test_wrapped_connect_timeout_stays_safe_in_chain():
    ct = _ConnectTimeout("connection timed out")
    wrapped = Exception("Stream iteration failed with recoverable error")
    wrapped.__cause__ = ct
    assert is_replay_unsafe_chain(wrapped) is False


# --- regression cases: tool turn must NOT replay post-dispatch failures ----

def test_tool_turn_instance_tools_surfaces_read_timeout():
    host = _RecordingHost(tools=["calc"])
    err = _ReadTimeout("read timed out")
    with pytest.raises(_ReadTimeout):
        host._stream_fallback_chat("hi", {"stream": True}, err)
    assert host.calls == [], "tool turn must not reissue after a post-dispatch failure"


def test_tool_turn_request_tools_surfaces_read_timeout():
    host = _RecordingHost(tools=None)
    err = _ReadTimeout("read timed out")
    with pytest.raises(_ReadTimeout):
        host._stream_fallback_chat("hi", {"stream": True, "tools": ["calc"]}, err)
    assert host.calls == []


def test_tool_turn_surfaces_wrapped_read_timeout():
    host = _RecordingHost(tools=["calc"])
    rt = _ReadTimeout("read timed out")
    wrapped = Exception("Stream iteration failed with recoverable error")
    wrapped.__cause__ = rt
    with pytest.raises(Exception) as exc_info:
        host._stream_fallback_chat("hi", {"stream": True}, wrapped)
    assert exc_info.value is wrapped
    assert host.calls == []


# --- controls: tool-less / pre-dispatch turns keep falling back ------------

def test_toolless_turn_still_falls_back_on_read_timeout():
    host = _RecordingHost(tools=None)
    err = _ReadTimeout("read timed out")
    result = host._stream_fallback_chat("hi", {"stream": True}, err)
    assert result == "sync answer"
    assert len(host.calls) == 1
    assert host.calls[0]["stream"] is False


def test_tool_turn_connect_timeout_still_falls_back():
    host = _RecordingHost(tools=["calc"])
    err = _ConnectTimeout("connection timed out")
    result = host._stream_fallback_chat("hi", {"stream": True}, err)
    assert result == "sync answer"
    assert len(host.calls) == 1
    assert host.calls[0]["stream"] is False


def test_tool_turn_generic_error_still_falls_back():
    host = _RecordingHost(tools=["calc"])
    result = host._stream_fallback_chat("hi", {"stream": True}, RuntimeError("boom"))
    assert result == "sync answer"
    assert len(host.calls) == 1
    assert host.calls[0]["stream"] is False


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-v"]))
