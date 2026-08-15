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


def test_late_result_lands_in_durable_sink_not_discarded_copy():
    # The real bug (Issue #3967 / reviewer P1): the native loop runs on a
    # per-call ``messages`` copy that is discarded once it returns. A background
    # job usually completes AFTER that, so the re-injection must target the
    # caller's durable history (e.g. the agent's ``chat_history``) — the list a
    # subsequent turn replays — not the transient copy.
    transient_loop_messages = []          # discarded after the loop returns
    durable_history = []                  # replayed on the next turn
    d = defer(note="queued job 100", handle_id="native-job-100")

    out = _handle_native_deferred_result(
        d, transient_loop_messages, "cid-4", "tool_d",
        history_sink=durable_history,
    )
    assert out == "queued job 100"

    # Simulate the loop finishing and its copy being discarded, then the
    # background job completing later.
    transient_loop_messages.clear()
    assert resolve_deferred("native-job-100", "late report") is True

    # Result survives in durable history; the discarded copy is untouched.
    assert transient_loop_messages == []
    assert durable_history == [
        {
            "role": "tool",
            "tool_call_id": "cid-4",
            "content": "[deferred:tool_d] late report",
        }
    ]


def test_no_sink_falls_back_to_messages_for_backward_compat():
    # Absent a durable sink, prior behaviour is preserved: an in-loop resolution
    # re-injects into ``messages`` so existing callers are unaffected.
    messages = []
    d = defer(note="queued job 101", handle_id="native-job-101")
    _handle_native_deferred_result(d, messages, "cid-5", "tool_e")
    assert resolve_deferred("native-job-101", "in-loop report") is True
    assert messages == [
        {
            "role": "tool",
            "tool_call_id": "cid-5",
            "content": "[deferred:tool_e] in-loop report",
        }
    ]


def test_early_resolution_delivers_to_durable_sink_immediately():
    # If the background job finishes before the loop registers (early
    # resolution), the buffered value is delivered on registration and must
    # still land in the durable sink.
    durable_history = []
    # Register-then-resolve is exercised above; here resolve first (buffered),
    # then register to confirm immediate delivery into the durable sink.
    assert resolve_deferred("native-job-102", "buffered report") is False
    d = defer(note="queued job 102", handle_id="native-job-102")
    _handle_native_deferred_result(
        d, [], "cid-6", "tool_f", history_sink=durable_history,
    )
    assert durable_history == [
        {
            "role": "tool",
            "tool_call_id": "cid-6",
            "content": "[deferred:tool_f] buffered report",
        }
    ]


if __name__ == "__main__":
    import sys
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
