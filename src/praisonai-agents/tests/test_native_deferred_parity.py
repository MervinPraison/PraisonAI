#!/usr/bin/env python3
"""Native-path deferred-tool-result parity tests (Issue #3967).

The LiteLLM loop already registers a ``DeferredToolResult`` on the shared
resolver so its eventual background value is re-injected. The native
OpenAI-SDK loop (``llm/openai_client.py``) previously stringified the handle
and lost it. These tests assert the native path now behaves identically:
a deferred handle is registered, the ``note`` is surfaced to the model now,
and a later ``resolve_deferred`` re-injects a follow-up tool message.
"""

from praisonaiagents.llm.openai_client import _handle_native_deferred_result
from praisonaiagents.tools.call_executor import (
    defer,
    get_deferred_resolver,
    resolve_deferred,
)


def test_plain_result_is_unchanged_and_not_registered():
    messages = []
    resolver = get_deferred_resolver()
    out = _handle_native_deferred_result("plain-value", messages, "cid-1", "tool_a")
    assert out == "plain-value"
    assert messages == []
    assert resolver.is_pending("cid-1") is False


def test_deferred_result_surfaces_note_and_registers_handle():
    messages = []
    resolver = get_deferred_resolver()
    d = defer(note="queued job 99", handle_id="native-job-99")

    out = _handle_native_deferred_result(d, messages, "cid-2", "tool_b")

    # Note surfaced to the model now instead of the raw handle object.
    assert out == "queued job 99"
    # Handle registered so the background result is not lost.
    assert resolver.is_pending("native-job-99") is True

    # Later background completion re-injects a follow-up tool message into the
    # same messages history the loop replays on the next turn.
    assert resolve_deferred("native-job-99", "final report") is True
    assert messages == [
        {
            "role": "tool",
            "tool_call_id": "cid-2",
            "content": "[deferred:tool_b] final report",
        }
    ]
    assert resolver.is_pending("native-job-99") is False


def test_registration_never_raises_on_bad_input():
    # A malformed deferred-like object must not break the turn; helper returns
    # the note attribute it can read and swallows any registration error.
    class _Broken:
        handle_id = None
        note = "still-runs"

    # Not a DeferredToolResult instance -> returned unchanged (safe default).
    out = _handle_native_deferred_result(_Broken(), [], "cid-3", "tool_c")
    assert isinstance(out, _Broken)


if __name__ == "__main__":
    import sys
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
