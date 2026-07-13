#!/usr/bin/env python3
"""Tests for per-tool timeout enforcement and structured error results.

Covers Issue #2957: the tool executor must enforce ToolExecutionConfig.timeout_ms,
support cancellation, and surface failures as discriminated structured errors
instead of an opaque "Error executing tool: ..." string.
"""

import threading
import time

from praisonaiagents.tools.call_executor import (
    ToolCall,
    ToolTimeoutError,
    ToolCancelledError,
    run_single_tool_call,
    SequentialToolCallExecutor,
    ParallelToolCallExecutor,
)


def _make_call(name="slow_tool"):
    return ToolCall(function_name=name, arguments={}, tool_call_id="tc-1")


def test_timeout_returns_typed_result():
    def execute(name, args, tool_call_id):
        time.sleep(2.0)
        return "done"

    result = run_single_tool_call(_make_call(), execute, timeout_ms=100)

    assert isinstance(result.error, ToolTimeoutError)
    assert result.error_kind == "timeout"
    assert result.result == {"error": "timeout", "timeout_ms": 100, "tool": "slow_tool"}
    se = result.structured_error
    assert se["kind"] == "timeout"
    assert se["tool"] == "slow_tool"


def test_within_timeout_succeeds():
    def execute(name, args, tool_call_id):
        return "quick"

    result = run_single_tool_call(_make_call(), execute, timeout_ms=1000)
    assert result.error is None
    assert result.result == "quick"


def test_no_timeout_preserves_behavior():
    def execute(name, args, tool_call_id):
        return "value"

    result = run_single_tool_call(_make_call(), execute)
    assert result.error is None
    assert result.result == "value"


def test_cancel_token_event_short_circuits():
    token = threading.Event()
    token.set()
    called = []

    def execute(name, args, tool_call_id):
        called.append(True)
        return "should not run"

    result = run_single_tool_call(_make_call(), execute, cancel_token=token)
    assert not called
    assert isinstance(result.error, ToolCancelledError)
    assert result.error_kind == "cancelled"
    assert result.structured_error["kind"] == "cancelled"


def test_error_is_structured_not_opaque():
    def execute(name, args, tool_call_id):
        raise PermissionError("nope")

    result = run_single_tool_call(_make_call(), execute)
    assert isinstance(result.error, PermissionError)
    se = result.structured_error
    assert se["kind"] == "error"
    assert se["type"] == "PermissionError"
    assert se["message"] == "nope"


def test_sequential_executor_forwards_timeout():
    def execute(name, args, tool_call_id):
        time.sleep(2.0)
        return "done"

    results = SequentialToolCallExecutor().execute_batch(
        [_make_call()], execute, timeout_ms=100
    )
    assert results[0].error_kind == "timeout"


def test_parallel_executor_forwards_timeout():
    def execute(name, args, tool_call_id):
        if name == "slow":
            time.sleep(2.0)
        return "done"

    calls = [
        ToolCall(function_name="slow", arguments={}, tool_call_id="a"),
        ToolCall(function_name="fast", arguments={}, tool_call_id="b"),
    ]
    results = ParallelToolCallExecutor().execute_batch(calls, execute, timeout_ms=200)
    assert results[0].error_kind == "timeout"
    assert results[1].error is None


def test_llm_reads_tool_timeout_ms_from_extra_settings():
    """Guard against regression where the timeout is accepted but never wired.

    The executor plumbing is opt-in via ``extra_settings['tool_timeout_ms']``;
    the ``LLM`` must store it so the tool-calling loop can forward it to
    ``execute_batch``. Defaults to ``None`` for zero regression.
    """
    import pytest

    llm_mod = pytest.importorskip("praisonaiagents.llm.llm")

    configured = llm_mod.LLM(model="gpt-4o-mini", tool_timeout_ms=1500)
    assert configured.tool_timeout_ms == 1500

    default = llm_mod.LLM(model="gpt-4o-mini")
    assert default.tool_timeout_ms is None
