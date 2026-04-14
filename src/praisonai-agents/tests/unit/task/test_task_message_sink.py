"""Tests for TaskMessageSinkProtocol (Gap 4).

Validates:
- Protocol structural subtyping
- NoOpTaskMessageSink (default — zero overhead)
- InMemoryTaskMessageSink for testing/debugging
- Sequenced messages with auto-incrementing seq_num
- Replay by task_id
- Message types: agent_output, tool_call, tool_result, error, status
- Registry pattern for sink management
"""
import pytest


class TestTaskMessageSinkProtocol:
    """Test the protocol definition."""

    def test_protocol_exists(self):
        from praisonaiagents.task.message_sink import TaskMessageSinkProtocol
        assert TaskMessageSinkProtocol is not None

    def test_noop_satisfies_protocol(self):
        from praisonaiagents.task.message_sink import TaskMessageSinkProtocol, NoOpTaskMessageSink
        sink = NoOpTaskMessageSink()
        assert isinstance(sink, TaskMessageSinkProtocol)

    def test_inmemory_satisfies_protocol(self):
        from praisonaiagents.task.message_sink import TaskMessageSinkProtocol, InMemoryTaskMessageSink
        sink = InMemoryTaskMessageSink()
        assert isinstance(sink, TaskMessageSinkProtocol)


class TestTaskMessage:
    """Test TaskMessage dataclass."""

    def test_message_creation(self):
        from praisonaiagents.task.message_sink import TaskMessage
        msg = TaskMessage(
            task_id="t1",
            seq_num=1,
            msg_type="agent_output",
            content="Hello world",
            agent_name="researcher",
        )
        assert msg.task_id == "t1"
        assert msg.seq_num == 1
        assert msg.msg_type == "agent_output"
        assert msg.content == "Hello world"
        assert msg.agent_name == "researcher"
        assert isinstance(msg.timestamp, str)

    def test_message_to_dict(self):
        from praisonaiagents.task.message_sink import TaskMessage
        msg = TaskMessage(
            task_id="t1",
            seq_num=0,
            msg_type="tool_call",
            content="search_web('AI')",
            agent_name="researcher",
        )
        d = msg.to_dict()
        assert d["task_id"] == "t1"
        assert d["msg_type"] == "tool_call"
        assert "timestamp" in d


class TestNoOpTaskMessageSink:
    """Test NoOp sink does nothing."""

    def test_emit_is_noop(self):
        from praisonaiagents.task.message_sink import NoOpTaskMessageSink, TaskMessage
        sink = NoOpTaskMessageSink()
        msg = TaskMessage(task_id="t1", seq_num=0, msg_type="agent_output", content="hi")
        sink.emit(msg)  # Should not raise

    def test_replay_returns_empty(self):
        from praisonaiagents.task.message_sink import NoOpTaskMessageSink
        sink = NoOpTaskMessageSink()
        assert sink.replay("t1") == []


class TestInMemoryTaskMessageSink:
    """Test InMemory sink stores and replays messages."""

    def test_emit_stores_message(self):
        from praisonaiagents.task.message_sink import InMemoryTaskMessageSink, TaskMessage
        sink = InMemoryTaskMessageSink()
        msg = TaskMessage(task_id="t1", seq_num=0, msg_type="agent_output", content="Hello")
        sink.emit(msg)
        assert len(sink.messages) == 1

    def test_replay_by_task_id(self):
        from praisonaiagents.task.message_sink import InMemoryTaskMessageSink, TaskMessage
        sink = InMemoryTaskMessageSink()
        sink.emit(TaskMessage(task_id="t1", seq_num=0, msg_type="agent_output", content="a"))
        sink.emit(TaskMessage(task_id="t2", seq_num=0, msg_type="agent_output", content="b"))
        sink.emit(TaskMessage(task_id="t1", seq_num=1, msg_type="tool_call", content="c"))
        result = sink.replay("t1")
        assert len(result) == 2
        assert result[0].seq_num == 0
        assert result[1].seq_num == 1

    def test_replay_ordered_by_seq_num(self):
        from praisonaiagents.task.message_sink import InMemoryTaskMessageSink, TaskMessage
        sink = InMemoryTaskMessageSink()
        # Insert out of order
        sink.emit(TaskMessage(task_id="t1", seq_num=2, msg_type="error", content="err"))
        sink.emit(TaskMessage(task_id="t1", seq_num=0, msg_type="agent_output", content="a"))
        sink.emit(TaskMessage(task_id="t1", seq_num=1, msg_type="tool_call", content="b"))
        result = sink.replay("t1")
        assert [m.seq_num for m in result] == [0, 1, 2]

    def test_clear(self):
        from praisonaiagents.task.message_sink import InMemoryTaskMessageSink, TaskMessage
        sink = InMemoryTaskMessageSink()
        sink.emit(TaskMessage(task_id="t1", seq_num=0, msg_type="agent_output", content="a"))
        sink.clear()
        assert len(sink.messages) == 0

    def test_message_types(self):
        from praisonaiagents.task.message_sink import InMemoryTaskMessageSink, TaskMessage
        sink = InMemoryTaskMessageSink()
        types = ["agent_output", "tool_call", "tool_result", "error", "status"]
        for i, t in enumerate(types):
            sink.emit(TaskMessage(task_id="t1", seq_num=i, msg_type=t, content=f"msg_{t}"))
        result = sink.replay("t1")
        assert len(result) == 5
        assert [m.msg_type for m in result] == types


class TestTaskMessageEmitter:
    """Test the convenience emitter that auto-sequences messages."""

    def test_emitter_auto_sequences(self):
        from praisonaiagents.task.message_sink import InMemoryTaskMessageSink, TaskMessageEmitter
        sink = InMemoryTaskMessageSink()
        emitter = TaskMessageEmitter(task_id="t1", sink=sink)
        emitter.emit("agent_output", "Hello")
        emitter.emit("tool_call", "search_web('AI')")
        emitter.emit("agent_output", "Done")
        result = sink.replay("t1")
        assert [m.seq_num for m in result] == [0, 1, 2]

    def test_emitter_with_agent_name(self):
        from praisonaiagents.task.message_sink import InMemoryTaskMessageSink, TaskMessageEmitter
        sink = InMemoryTaskMessageSink()
        emitter = TaskMessageEmitter(task_id="t1", sink=sink, agent_name="researcher")
        emitter.emit("agent_output", "result")
        assert sink.messages[0].agent_name == "researcher"

    def test_emitter_with_noop_sink(self):
        """Emitter works with NoOp sink (zero overhead)."""
        from praisonaiagents.task.message_sink import NoOpTaskMessageSink, TaskMessageEmitter
        sink = NoOpTaskMessageSink()
        emitter = TaskMessageEmitter(task_id="t1", sink=sink)
        emitter.emit("agent_output", "Hello")  # Should not raise
