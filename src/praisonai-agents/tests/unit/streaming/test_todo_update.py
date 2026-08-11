"""
Unit tests for the live TODO_UPDATED stream event and its emission from the
built-in todo tool, including the async tool-execution path.

Covers:
- TODO_UPDATED event type exists
- emit_todo_update is a no-op (returns False) when no sink is active
- emit_todo_update forwards the full ordered list to an active sink
- TodoTools.todo_add / todo_update emit TODO_UPDATED under an active channel
- The single-in_progress invariant (starting one demotes any other)
- The async tool-execution path installs the progress channel so
  emit_todo_update / emit_tool_progress reach a subscribed stream emitter
"""

import asyncio
import os

import pytest

from praisonaiagents.streaming.events import (
    StreamEvent,
    StreamEventType,
    emit_todo_update,
    tool_progress_channel,
)


class TestTodoUpdateEvent:
    def test_todo_updated_event_type_exists(self):
        assert StreamEventType.TODO_UPDATED.value == "todo_updated"

    def test_emit_is_noop_without_sink(self):
        assert emit_todo_update([{"id": 1, "task": "x"}]) is False

    def test_emit_forwards_full_list(self):
        events = []
        todos = [{"id": 1, "task": "a"}, {"id": 2, "task": "b"}]
        with tool_progress_channel(events.append):
            assert emit_todo_update(todos) is True
        assert len(events) == 1
        evt = events[0]
        assert evt.type == StreamEventType.TODO_UPDATED
        assert evt.metadata["todos"] == todos


class TestTodoToolsEmission:
    @pytest.fixture(autouse=True)
    def _auto_approve(self, monkeypatch):
        # todo_add / todo_update are @require_approval; auto-approve for tests.
        monkeypatch.setenv("PRAISONAI_AUTO_APPROVE", "true")

    def _tools(self, tmp_path):
        from praisonaiagents.tools.todo_tools import TodoTools

        t = TodoTools()
        t._todo_file = str(tmp_path / "todos.json")
        return t

    def test_todo_add_emits(self, tmp_path):
        t = self._tools(tmp_path)
        events = []
        with tool_progress_channel(events.append):
            t.todo_add("first task")
        assert [e.type for e in events] == [StreamEventType.TODO_UPDATED]
        assert events[0].metadata["todos"][0]["task"] == "first task"

    def test_todo_update_single_in_progress(self, tmp_path):
        t = self._tools(tmp_path)
        t.todo_add("task one")
        t.todo_add("task two")
        events = []
        with tool_progress_channel(events.append):
            t.todo_update(1, status="in_progress")
            t.todo_update(2, status="in_progress")
        # Two mutations -> two TODO_UPDATED events.
        assert len(events) == 2
        final = events[-1].metadata["todos"]
        in_progress = [x for x in final if x["status"] == "in_progress"]
        assert len(in_progress) == 1
        assert in_progress[0]["id"] == 2
        # The previously-active item was demoted back to pending.
        assert next(x for x in final if x["id"] == 1)["status"] == "pending"


class _StubEmitter:
    """Minimal stand-in for the agent stream emitter used by the async path."""

    def __init__(self):
        self.events = []

    @property
    def has_callbacks(self):
        return True

    def emit(self, event):
        self.events.append(event)


class TestAsyncToolExecutionChannel:
    def test_async_path_installs_progress_channel(self):
        """A sync tool run through the async execution impl must see an active
        progress channel so emit_todo_update / emit_tool_progress reach the
        subscribed emitter (regression: async path lost the sink)."""
        from praisonaiagents.agent.execution_mixin import ExecutionMixin

        class _Agent(ExecutionMixin):
            name = "tester"

            def __init__(self, emitter):
                self._stream_emitter = emitter

            def _get_existing_stream_emitter(self):
                return self._stream_emitter

            async def _check_tool_approval_async(self, function_name, arguments):
                return (function_name, arguments)

            def _check_tool_policy_and_guardrails(self, function_name, arguments):
                return (function_name, arguments)

        def my_tool():
            # A tool that publishes a live todo update while running.
            emit_todo_update([{"id": 1, "task": "from-tool", "status": "pending"}])
            return "ok"

        emitter = _StubEmitter()
        agent = _Agent(emitter)
        agent.tools = [my_tool]

        result = asyncio.run(
            agent._execute_tool_async_impl("my_tool", {})
        )

        assert result == "ok" or (
            isinstance(result, dict) and result.get("result") == "ok"
        )
        todo_events = [
            e for e in emitter.events if e.type == StreamEventType.TODO_UPDATED
        ]
        assert len(todo_events) == 1
        assert todo_events[0].metadata["todos"][0]["task"] == "from-tool"
        # The forwarding sink annotates the event with the tool name / agent id.
        assert todo_events[0].tool_call["name"] == "my_tool"
        assert todo_events[0].agent_id == "tester"
