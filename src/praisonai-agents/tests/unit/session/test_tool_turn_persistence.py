"""
Issue #3089: the default file-backed session store must persist tool-call and
tool-result turns so resuming a tool-using agent reconstructs the same message
list the model saw before — not a text-only summary of it.
"""

import tempfile

import pytest

from praisonaiagents.session.store import DefaultSessionStore, SessionMessage


@pytest.fixture
def temp_store():
    with tempfile.TemporaryDirectory() as tmpdir:
        yield DefaultSessionStore(session_dir=tmpdir)


TOOL_CALLS = [
    {
        "id": "call_1",
        "type": "function",
        "function": {"name": "read_file", "arguments": '{"path": "a.txt"}'},
    }
]


class TestSessionMessageToolFields:
    def test_tool_fields_round_trip(self):
        assistant = SessionMessage(role="assistant", content="", tool_calls=TOOL_CALLS)
        result = SessionMessage(role="tool", content="body", tool_call_id="call_1")

        assert SessionMessage.from_dict(assistant.to_dict()).tool_calls == TOOL_CALLS
        assert SessionMessage.from_dict(result.to_dict()).tool_call_id == "call_1"

    def test_text_turn_keeps_legacy_four_key_shape(self):
        d = SessionMessage(role="user", content="hi").to_dict()
        assert set(d.keys()) == {"role", "content", "timestamp", "metadata"}

    def test_old_format_file_loads_unchanged(self):
        msg = SessionMessage.from_dict({"role": "assistant", "content": "hello"})
        assert msg.tool_calls is None
        assert msg.tool_call_id is None
        assert msg.to_llm_message() == {"role": "assistant", "content": "hello"}


class TestResumeRoundTrip:
    def test_resume_preserves_tool_turns_in_order(self, temp_store):
        temp_store.add_user_message("s1", "read a.txt")
        temp_store.add_message("s1", "assistant", "", tool_calls=TOOL_CALLS)
        temp_store.add_message("s1", "tool", "file body", tool_call_id="call_1")
        temp_store.add_assistant_message("s1", "Here is the file.")

        history = temp_store.get_chat_history("s1")

        assert [m["role"] for m in history] == [
            "user",
            "assistant",
            "tool",
            "assistant",
        ]
        assert history[1]["tool_calls"] == TOOL_CALLS
        assert history[2]["tool_call_id"] == "call_1"
        # Text turns stay minimal — no spurious tool keys.
        assert "tool_calls" not in history[0]
        assert "tool_call_id" not in history[3]

    def test_resume_survives_new_store_instance(self, temp_store):
        temp_store.add_message("s2", "assistant", "", tool_calls=TOOL_CALLS)
        temp_store.add_message("s2", "tool", "ok", tool_call_id="call_1")

        reopened = DefaultSessionStore(session_dir=temp_store.session_dir)
        history = reopened.get_chat_history("s2")
        assert history[0]["tool_calls"] == TOOL_CALLS
        assert history[1]["tool_call_id"] == "call_1"

    def test_set_chat_history_preserves_tool_turns(self, temp_store):
        messages = [
            {"role": "user", "content": "go"},
            {"role": "assistant", "content": "", "tool_calls": TOOL_CALLS},
            {"role": "tool", "content": "ok", "tool_call_id": "call_1"},
        ]
        temp_store.set_chat_history("s3", messages)

        history = temp_store.get_chat_history("s3")
        assert history[1]["tool_calls"] == TOOL_CALLS
        assert history[2]["tool_call_id"] == "call_1"


class TestPersistMessageForwardsToolTurns:
    def test_persist_message_writes_tool_turns(self, temp_store):
        from praisonaiagents import Agent

        agent = Agent(name="t", instructions="t")
        agent._db = None
        agent._session_store = temp_store
        agent._session_id = "s4"

        agent._persist_message("user", "go")
        agent._persist_message("assistant", "", tool_calls=TOOL_CALLS)
        agent._persist_message("tool", "result", tool_call_id="call_1")

        history = temp_store.get_chat_history("s4")
        assert [m["role"] for m in history] == ["user", "assistant", "tool"]
        assert history[1]["tool_calls"] == TOOL_CALLS
        assert history[2]["tool_call_id"] == "call_1"


class _LegacyStore:
    """A store matching the pre-#3089 SessionStoreProtocol shape: its
    ``add_message`` does not accept tool_calls / tool_call_id kwargs."""

    def __init__(self):
        self.calls = []

    def add_user_message(self, session_id, content):
        self.calls.append(("user", content))

    def add_assistant_message(self, session_id, content):
        self.calls.append(("assistant", content))

    def add_message(self, session_id, role, content, metadata=None):
        self.calls.append((role, content))


class TestLegacyStoreCompatibility:
    """Issue #3089: stores predating the tool fields must not raise and must
    not silently drop the turn — the turn is preserved as plain text."""

    def test_persist_message_falls_back_for_legacy_store(self):
        from praisonaiagents import Agent

        agent = Agent(name="t", instructions="t")
        agent._db = None
        agent._session_store = _LegacyStore()
        agent._session_id = "s5"

        agent._persist_message("assistant", "call", tool_calls=TOOL_CALLS)
        agent._persist_message("tool", "result", tool_call_id="call_1")

        assert agent._session_store.calls == [
            ("assistant", "call"),
            ("tool", "result"),
        ]

    def test_hierarchical_store_accepts_tool_fields(self):
        import tempfile
        from praisonaiagents.session.hierarchy import HierarchicalSessionStore

        with tempfile.TemporaryDirectory() as tmpdir:
            store = HierarchicalSessionStore(session_dir=tmpdir)
            store.add_message("h1", "assistant", "", tool_calls=TOOL_CALLS)
            store.add_message("h1", "tool", "ok", tool_call_id="call_1")

            history = store.get_chat_history("h1")
            assert history[0].get("tool_calls") == TOOL_CALLS
            assert history[1].get("tool_call_id") == "call_1"


class TestHistoryLimitPreservesToolExchanges:
    """Issue #3089: a count-based tail must not begin on an orphaned tool
    result whose assistant tool-call was trimmed off."""

    def test_get_chat_history_skips_orphaned_tool_result(self, temp_store):
        temp_store.add_user_message("s6", "go")
        temp_store.add_message("s6", "assistant", "", tool_calls=TOOL_CALLS)
        temp_store.add_message("s6", "tool", "result", tool_call_id="call_1")
        temp_store.add_assistant_message("s6", "done")

        # max_messages=2 would naively slice ["tool", "assistant"], orphaning
        # the tool result. The boundary must skip forward past it.
        history = temp_store.get_chat_history("s6", max_messages=2)
        assert history[0]["role"] != "tool"
