"""Tests for the /recap bot command handler.

/recap renders a read-only "where were we" summary from the user's existing
history without mutating the conversation or triggering compaction.
"""

import copy

from praisonai_bot.bots._commands import (
    CommandRegistry,
    handle_recap_command,
)


class FakeSession:
    """Minimal stand-in for BotSessionManager used by the handler."""

    def __init__(self, histories=None):
        self._histories = histories or {}

    def _storage_key(self, user_id):
        return user_id


def _history(n=8):
    msgs = [{"role": "system", "content": "You are a helpful agent."}]
    for i in range(n):
        msgs.append({"role": "user", "content": f"user message {i}"})
        msgs.append({"role": "assistant", "content": f"assistant reply {i}"})
    return msgs


def test_recap_command_registered():
    registry = CommandRegistry()
    assert "recap" in registry.get_command_names()
    assert registry.get_command("recap")["builtin"] is True


def test_bot_recap_renders_summary():
    session = FakeSession({"u1": _history(3)})
    out = handle_recap_command(session, "u1")
    assert isinstance(out, str) and out
    assert "assistant reply 2" in out  # recent tail surfaced


def test_bot_recap_nondestructive():
    """/recap must not mutate the stored history nor trigger compaction."""
    history = _history()
    session = FakeSession({"u1": history})
    before = copy.deepcopy(history)
    handle_recap_command(session, "u1")
    assert session._histories["u1"] == before


def test_bot_recap_empty_history():
    session = FakeSession({"u1": []})
    assert "Nothing to recap" in handle_recap_command(session, "u1")


def test_bot_recap_no_history_key():
    session = FakeSession({})
    assert "Nothing to recap" in handle_recap_command(session, "u1")
