"""Regression tests for durable-aware async tool callback dispatch."""

import contextvars
import threading
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from praisonaiagents.llm.llm import _dispatch_async_tool
from praisonaiagents.errors import ToolExecutionError
from praisonaiagents.llm.llm import LLM


def _responses_llm(monkeypatch):
    llm = LLM(model="openai/gpt-4o-mini", api_key="test")
    tool_call = {
        "id": "call-1",
        "type": "function",
        "function": {"name": "noop", "arguments": "{}"},
    }
    monkeypatch.setattr(llm, "_supports_responses_api", lambda: True)
    monkeypatch.setattr(llm, "_build_responses_params", lambda **kwargs: {})
    monkeypatch.setattr(
        llm,
        "_extract_from_responses_output",
        lambda _response: ("", [tool_call], None),
    )
    return llm


@pytest.mark.asyncio
async def test_sync_tool_callback_runs_off_loop_with_context():
    caller_thread = threading.get_ident()
    marker = contextvars.ContextVar("durable-dispatch-marker", default="missing")
    marker.set("present")

    def execute(_name, _arguments, *, tool_call_id=None, **kwargs):
        return threading.get_ident(), marker.get(), tool_call_id, kwargs

    execute._accepts_durable_iteration = True
    result = await _dispatch_async_tool(execute, "tool", {}, "call-1", 4)

    assert result[0] != caller_thread
    assert result[1:] == (
        "present",
        "call-1",
        {"_durable_iteration_index": 4},
    )


@pytest.mark.asyncio
async def test_async_tool_callback_is_awaited():
    async def execute(_name, _arguments, *, tool_call_id=None):
        return f"done:{tool_call_id}"

    assert await _dispatch_async_tool(execute, "tool", {}, "call-2", 2) == (
        "done:call-2"
    )


def test_sync_response_loop_finalizes_per_call_iteration_limit(monkeypatch):
    llm = _responses_llm(monkeypatch)
    monkeypatch.setattr(llm, "_call_responses_api", lambda **kwargs: object())
    finalise = MagicMock(return_value="finalized")
    monkeypatch.setattr(llm, "_finalise_on_limit", finalise)

    with patch(
        "praisonaiagents.llm.llm._get_display_functions",
        return_value={"execute_sync_callback": MagicMock()},
    ):
        result = llm.get_response(
            prompt="task",
            tools=[lambda: None],
            execute_tool_fn=lambda *_args, **_kwargs: "ok",
            stream=False,
            verbose=False,
            max_iterations=1,
        )

    assert result == "finalized"
    finalise.assert_called_once()
    assert llm._last_stop_reason == "max_steps"


@pytest.mark.asyncio
async def test_async_response_loop_finalizes_per_call_iteration_limit(
    monkeypatch,
):
    llm = _responses_llm(monkeypatch)
    monkeypatch.setattr(
        llm, "_call_responses_api_async", AsyncMock(return_value=object())
    )
    finalise = AsyncMock(return_value="finalized")
    monkeypatch.setattr(llm, "_finalise_on_limit_async", finalise)

    with patch(
        "praisonaiagents.llm.llm._get_display_functions",
        return_value={"execute_sync_callback": MagicMock()},
    ):
        result = await llm.get_response_async(
            prompt="task",
            tools=[lambda: None],
            execute_tool_fn=lambda *_args, **_kwargs: "ok",
            stream=False,
            verbose=False,
            max_iterations=1,
        )

    assert result == "finalized"
    finalise.assert_awaited_once()
    assert llm._last_stop_reason == "max_steps"


def test_sync_response_loop_preserves_terminal_tool_error(monkeypatch):
    llm = _responses_llm(monkeypatch)
    monkeypatch.setattr(llm, "_call_responses_api", lambda **kwargs: object())
    error = ToolExecutionError("halt", tool_name="noop", is_retryable=False)

    def execute(*_args, **_kwargs):
        raise error

    with (
        patch(
            "praisonaiagents.llm.llm._get_display_functions",
            return_value={
                "execute_sync_callback": MagicMock(),
                "display_error": MagicMock(),
            },
        ),
        pytest.raises(ToolExecutionError, match="halt"),
    ):
        llm.get_response(
            prompt="task",
            tools=[lambda: None],
            execute_tool_fn=execute,
            stream=False,
            verbose=False,
            max_iterations=1,
        )
