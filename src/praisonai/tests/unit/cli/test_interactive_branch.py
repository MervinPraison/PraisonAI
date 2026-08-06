"""Tests for the REPL `/branch` command (Issue #3731).

`/branch [title]` forks the live conversation mid-session, switches the REPL
onto the fork (rebinding the session id + reloading history), and keeps the
parent timeline resumable. `/branch --at N` forks from N user turns back.
"""

import tempfile
from pathlib import Path

import pytest

from praisonai.cli.legacy.interactive_legacy import _handle_branch_command
from praisonai.cli.session.unified import UnifiedSession, UnifiedSessionStore


class _RecordingConsole:
    def __init__(self):
        self.lines = []

    def print(self, *args, **kwargs):
        self.lines.append(" ".join(str(a) for a in args))


@pytest.fixture
def temp_session_dir():
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


def _seeded_state(store):
    session = store.get_or_create("parent")
    session.add_user_message("first")
    session.add_assistant_message("reply-1")
    session.add_user_message("second")
    session.add_assistant_message("reply-2")
    store.save(session)
    session = store.load("parent")
    return {
        "session_store": store,
        "unified_session": session,
        "conversation_history": session.get_chat_history(),
    }


def test_branch_mid_session_creates_child_and_switches(temp_session_dir):
    store = UnifiedSessionStore(session_dir=temp_session_dir)
    state = _seeded_state(store)
    console = _RecordingConsole()

    _handle_branch_command(None, console, "alt approach", state)

    new_session = state["unified_session"]
    # Switched onto the fork.
    assert new_session.session_id != "parent"
    assert new_session.parent_id == "parent"
    assert new_session.metadata.get("title") == "alt approach"
    # History reloaded from the fork.
    assert state["conversation_history"] == new_session.get_chat_history()

    # Both timelines listable/resumable; lineage recorded on the parent.
    parent = store.load("parent")
    assert new_session.session_id in parent.children_ids
    assert store.load(new_session.session_id) is not None


def test_branch_at_n_truncates_to_index(temp_session_dir):
    store = UnifiedSessionStore(session_dir=temp_session_dir)
    state = _seeded_state(store)
    console = _RecordingConsole()

    # One user turn back = fork just before the last user message.
    _handle_branch_command(None, console, "--at 1", state)

    fork = state["unified_session"]
    # Keeps first user + first reply + second user (index of last user turn).
    assert fork.messages[-1]["role"] == "user"
    assert fork.messages[-1]["content"] == "second"
    assert fork.message_count == 3
    # Parent untouched.
    assert store.load("parent").message_count == 4


def test_branch_at_too_far_back_is_rejected(temp_session_dir):
    store = UnifiedSessionStore(session_dir=temp_session_dir)
    state = _seeded_state(store)
    console = _RecordingConsole()

    _handle_branch_command(None, console, "--at 99", state)

    # No fork created; still on parent.
    assert state["unified_session"].session_id == "parent"
    assert any("user turns available" in line for line in console.lines)
