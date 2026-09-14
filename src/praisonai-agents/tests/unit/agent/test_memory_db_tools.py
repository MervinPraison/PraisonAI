"""
Issue #5075: the DbAdapter persistence path must persist tool-call and
tool-result turns (and restore them on resume) with the same faithfulness the
default JSON session store gained in Issue #3089. Without this, tool-using
agents on database backends receive a broken transcript after resume.
"""

from unittest.mock import MagicMock

import pytest

from praisonaiagents import Agent
from praisonaiagents.db.protocol import DbMessage


TOOL_CALLS = [
    {
        "id": "call_1",
        "type": "function",
        "function": {"name": "read_file", "arguments": '{"path": "a.txt"}'},
    }
]


def _db_agent(db):
    agent = Agent(name="t", instructions="t")
    agent._db = db
    agent._session_store = None
    agent._session_id = "sess-1"
    agent._db_initialized = True
    return agent


class TestPersistForwardsToolTurnsToDb:
    def test_assistant_tool_calls_go_to_on_assistant_message(self):
        db = MagicMock()
        agent = _db_agent(db)

        agent._persist_message("assistant", "", tool_calls=TOOL_CALLS)

        db.on_assistant_message.assert_called_once()
        args, kwargs = db.on_assistant_message.call_args
        assert kwargs.get("tool_calls") == TOOL_CALLS
        # Text-only agent-message path is not used for a tool-call turn.
        db.on_agent_message.assert_not_called()

    def test_tool_result_goes_to_on_tool_message(self):
        db = MagicMock()
        agent = _db_agent(db)

        agent._persist_message("tool", "result body", tool_call_id="call_1")

        db.on_tool_message.assert_called_once()
        args, kwargs = db.on_tool_message.call_args
        assert kwargs.get("tool_call_id") == "call_1"

    def test_plain_assistant_turn_still_uses_on_agent_message(self):
        db = MagicMock()
        agent = _db_agent(db)

        agent._persist_message("assistant", "hello")

        db.on_agent_message.assert_called_once_with("sess-1", "hello")
        db.on_assistant_message.assert_not_called()

    def test_user_turn_unchanged(self):
        db = MagicMock()
        agent = _db_agent(db)

        agent._persist_message("user", "hi")

        db.on_user_message.assert_called_once_with("sess-1", "hi")


class _LegacyDb:
    """A DbAdapter predating the tool-turn callbacks: it exposes only the
    original user/agent message methods. Tool turns must not raise and the
    assistant tool-call turn falls back to text-only on_agent_message."""

    def __init__(self):
        self.agent_calls = []
        self.user_calls = []

    def on_user_message(self, session_id, content, metadata=None):
        self.user_calls.append(content)

    def on_agent_message(self, session_id, content, metadata=None):
        self.agent_calls.append(content)


class TestLegacyDbBackwardCompatible:
    def test_legacy_db_falls_back_to_text_only(self):
        db = _LegacyDb()
        agent = _db_agent(db)

        # Should not raise even though on_assistant_message / on_tool_message
        # are absent.
        agent._persist_message("assistant", "call", tool_calls=TOOL_CALLS)
        agent._persist_message("tool", "result", tool_call_id="call_1")

        # Assistant tool-call turn preserved as text; tool turn dropped as
        # before (unchanged legacy behaviour).
        assert db.agent_calls == ["call"]


class TestDbResumeRestoresToolShape:
    def test_resume_rebuilds_full_llm_message_list(self):
        history = [
            DbMessage(role="user", content="read a.txt"),
            DbMessage(role="assistant", content="", tool_calls=TOOL_CALLS),
            DbMessage(role="tool", content="file body", tool_call_id="call_1"),
            DbMessage(role="assistant", content="Here is the file."),
        ]
        db = MagicMock()
        db.on_agent_start.return_value = history

        agent = Agent(name="t", instructions="t")
        agent._db = db
        agent._session_id = "sess-resume"
        agent._db_initialized = False
        # Restore runs lazily on first chat; invoke it directly with our mock
        # history to assert the rebuilt transcript shape.
        agent._init_db_session()

        roles = [m["role"] for m in agent.chat_history]
        assert roles == ["user", "assistant", "tool", "assistant"]
        assert agent.chat_history[1]["tool_calls"] == TOOL_CALLS
        assert agent.chat_history[2]["tool_call_id"] == "call_1"
        # Plain turns stay minimal — no spurious tool keys.
        assert "tool_calls" not in agent.chat_history[0]
        assert "tool_call_id" not in agent.chat_history[3]
