"""Tests for the conversation-control built-in chat commands.

Covers the new /undo, /sessions, /resume, /retry and /reasoning handlers that
wire existing core primitives onto the shared bot command registry. These run
without any platform SDK by exercising the shared handlers directly.
"""

from praisonai.bots._commands import (
    CommandRegistry,
    handle_undo_command,
    handle_sessions_command,
    handle_resume_command,
    handle_retry_command,
    handle_reasoning_command,
)


class FakeSession:
    """Minimal stand-in for BotSessionManager used by the handlers."""

    def __init__(self, histories=None):
        self._histories = histories or {}

    def _storage_key(self, user_id):
        return user_id


class FakeAgent:
    def __init__(self, undo_result=True, raises=False):
        self._undo_result = undo_result
        self._raises = raises

    def undo(self):
        if self._raises:
            raise RuntimeError("boom")
        return self._undo_result


def test_new_commands_registered():
    registry = CommandRegistry()
    names = registry.get_command_names()
    for cmd in ("undo", "sessions", "resume", "retry", "reasoning"):
        assert cmd in names
        assert registry.get_command(cmd)["builtin"] is True


def test_undo_reverts_when_agent_supports_it():
    assert handle_undo_command(FakeAgent(undo_result=True)) == "✅ Reverted the last turn."


def test_undo_nothing_to_undo():
    assert handle_undo_command(FakeAgent(undo_result=False)) == "ℹ️ Nothing to undo."


def test_undo_without_agent():
    assert "no agent" in handle_undo_command(None).lower()


def test_undo_without_support():
    class NoUndo:
        pass

    assert "does not support undo" in handle_undo_command(NoUndo())


def test_undo_surfaces_errors():
    assert "Could not undo" in handle_undo_command(FakeAgent(raises=True))


def test_sessions_lists_keys():
    session = FakeSession({"u1": [], "u2": []})
    out = handle_sessions_command(session, "u1")
    assert "u1" in out and "u2" in out


def test_sessions_empty():
    assert handle_sessions_command(FakeSession({}), "u1") == "No saved sessions yet."


def test_resume_requires_id():
    assert "Usage" in handle_resume_command(FakeSession({}), "u1", None)


def test_resume_found_in_history():
    session = FakeSession({"abc": [{"role": "user", "content": "hi"}]})
    out = handle_resume_command(session, "u1", "abc")
    assert "available" in out


def test_resume_not_found():
    out = handle_resume_command(FakeSession({}), "u1", "missing")
    assert "not found" in out


def test_resume_prefers_resume_session_hook():
    class Session(FakeSession):
        def resume_session(self, user_id, session_id):
            return session_id == "ok"

    assert "Resumed" in handle_resume_command(Session(), "u1", "ok")
    assert "not found" in handle_resume_command(Session(), "u1", "nope")


def test_retry_returns_last_user_message():
    history = {
        "u1": [
            {"role": "user", "content": "first"},
            {"role": "assistant", "content": "reply"},
            {"role": "user", "content": "second"},
            {"role": "assistant", "content": "reply2"},
        ]
    }
    out = handle_retry_command(FakeSession(history), "u1")
    assert "second" in out


def test_retry_nothing_to_retry():
    out = handle_retry_command(FakeSession({"u1": []}), "u1")
    assert "Nothing to retry" in out


def test_reasoning_toggles_state():
    session = FakeSession({})
    first = handle_reasoning_command(session, "u1")
    second = handle_reasoning_command(session, "u1")
    assert "shown" in first
    assert "hidden" in second
    # Preference is persisted on the session manager.
    assert session._reasoning_visibility["u1"] is False
