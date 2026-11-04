"""Chat-history integrity for tool turns (Issue #6217)."""
import pytest

from praisonaiagents import Agent
from praisonaiagents.config import MemoryConfig
from praisonaiagents.session import DefaultSessionStore


def _tool_history():
    return [
        {"role": "user", "content": "weather in Paris?"},
        {"role": "assistant", "content": None, "tool_calls": [{
            "id": "call_1", "type": "function",
            "function": {"name": "weather", "arguments": "{\"city\":\"Paris\"}"},
        }]},
        {"role": "tool", "tool_call_id": "call_1", "content": "18C sunny"},
        {"role": "assistant", "content": "It is 18C and sunny."},
    ]


def _agent(session_id=None, store=None):
    kwargs = {}
    if session_id:
        kwargs["memory"] = MemoryConfig(history=True, auto_save=session_id)
    a = Agent(name="a", instructions="x", model="gpt-4o-mini", **kwargs)
    if store is not None:
        a._session_store = store
        a._init_session_store()
    return a


@pytest.fixture
def store(tmp_path):
    return DefaultSessionStore(session_dir=str(tmp_path))


def _roles(a):
    return [m["role"] for m in a.chat_history]


def test_auto_save_round_trips_tool_fields(store):
    a = _agent("sess_rt", store)
    a.chat_history.extend(_tool_history())
    a._auto_save_session()

    b = _agent("sess_rt", store)
    restored = b.chat_history
    assert restored[1]["tool_calls"][0]["id"] == "call_1"
    assert restored[2]["tool_call_id"] == "call_1"
    assert restored[2]["content"] == "18C sunny"


def test_replace_chat_history_resyncs_auto_save_cursor(store):
    a = _agent("sess_cmp", store)

    def turn(i):
        a._append_to_chat_history({"role": "user", "content": f"q{i}"})
        a._append_to_chat_history({"role": "assistant", "content": f"a{i}"})
        a._auto_save_session()

    for i in range(3):
        turn(i)
    a._replace_chat_history([
        {"role": "system", "content": "summary"},
        {"role": "assistant", "content": "a2"},
    ])
    for i in range(3, 6):
        turn(i)
    saved = [m["content"] for m in store.get_chat_history("sess_cmp")]
    assert saved == ["q0", "a0", "q1", "a1", "q2", "a2",
                     "q3", "a3", "q4", "a4", "q5", "a5"]


def test_replace_chat_history_keeps_unsaved_survivors(store):
    a = _agent("sess_unsaved", store)
    a._append_to_chat_history({"role": "user", "content": "q0"})
    a._auto_save_session()
    pending = {"role": "user", "content": "q1"}
    a._append_to_chat_history(pending)
    # Compaction mid-turn keeps the not-yet-saved message in its tail.
    a._replace_chat_history([{"role": "system", "content": "summary"}, pending])
    a._auto_save_session()
    saved = [m["content"] for m in store.get_chat_history("sess_unsaved")]
    assert saved == ["q0", "q1"]


def test_replace_chat_history_saves_appended_messages(store):
    # Durable resume appends replayed tool pairs to a fully-saved history.
    a = _agent("sess_replay", store)
    a._append_to_chat_history({"role": "user", "content": "q0"})
    a._auto_save_session()
    replay = _tool_history()[1:3]
    a._replace_chat_history(list(a.chat_history) + replay)
    a._auto_save_session()
    saved = store.get_chat_history("sess_replay")
    assert [m["role"] for m in saved] == ["user", "assistant", "tool"]
    assert saved[2]["tool_call_id"] == "call_1"


def test_prune_history_does_not_orphan_tool_result():
    a = _agent()
    a.chat_history.extend(_tool_history())
    a.prune_history(keep_last=2)
    assert _roles(a) == ["assistant"]


def test_delete_history_removes_whole_exchange():
    for idx in (1, 2):
        a = _agent()
        a.chat_history.extend(_tool_history())
        assert a.delete_history(idx) is True
        assert _roles(a) == ["user", "assistant"]
    a = _agent()
    a.chat_history.extend(_tool_history())
    assert a.delete_history(10) is False
    assert a.delete_history(-1) is True
    assert len(a.chat_history) == 3


def test_truncate_does_not_leave_dangling_tool_calls():
    a = _agent()
    a.chat_history.extend(_tool_history())
    a._truncate_chat_history(2)
    assert _roles(a) == ["user"]
    a = _agent()
    a.chat_history.extend(_tool_history())
    a._truncate_chat_history(3)
    assert len(a.chat_history) == 3


def test_delete_history_matching_tolerates_none_content():
    a = _agent()
    a.chat_history.extend(_tool_history())
    assert a.delete_history_matching("image") == 0
    # A hit on the tool result drops its whole exchange.
    assert a.delete_history_matching("18c sunny") == 2
    assert _roles(a) == ["user", "assistant"]
