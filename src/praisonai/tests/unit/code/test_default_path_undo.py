"""
Tests for coherent turn-level undo/revert on the *default* CLI path.

The proven ``SessionCheckpointManager`` engine was previously reachable only
from the legacy REPL / debug TUI and defaulted off inconsistently. These tests
assert the wiring added to the modern surfaces:

- ``SessionCheckpointManager.from_config`` honours an explicit ``default`` so a
  single ``checkpoints.auto`` key drives both the file-only run checkpoints and
  the coherent turn-revert (no split default);
- the modern REPL's in-memory conversation adapter rewinds history in lockstep
  with the workspace files when ``/undo`` / ``/revert`` run;
- after an agent edit, ``/undo`` restores both the file **and** the conversation
  length to the prior turn boundary.
"""

import os
import tempfile

import pytest

from praisonai.cli.features.session_checkpoints import SessionCheckpointManager
from praisonai_code.cli.interactive.repl import (
    InteractiveREPL,
    REPLConfig,
    _InMemoryConversationStore,
)


def _write(path, content):
    with open(path, "w") as f:
        f.write(content)


def test_from_config_default_true_enables_when_key_absent(monkeypatch):
    """Interactive surfaces pass default=True so absence of the key is on."""
    monkeypatch.delenv("PRAISONAI_CHECKPOINTS", raising=False)
    with tempfile.TemporaryDirectory() as workspace:
        mgr = SessionCheckpointManager.from_config(
            workspace_dir=workspace, config=None, default=True
        )
        assert mgr.enabled is True


def test_from_config_default_true_still_respects_explicit_false(monkeypatch):
    """An explicit checkpoints.auto: false opts out even with default=True."""
    monkeypatch.delenv("PRAISONAI_CHECKPOINTS", raising=False)
    with tempfile.TemporaryDirectory() as workspace:
        mgr = SessionCheckpointManager.from_config(
            workspace_dir=workspace,
            config={"checkpoints": {"auto": False}},
            default=True,
        )
        assert mgr.enabled is False


def test_from_config_default_false_preserves_zero_overhead(monkeypatch):
    """Programmatic default is unchanged (disabled) for backward-compat."""
    monkeypatch.delenv("PRAISONAI_CHECKPOINTS", raising=False)
    with tempfile.TemporaryDirectory() as workspace:
        mgr = SessionCheckpointManager.from_config(workspace_dir=workspace)
        assert mgr.enabled is False


def test_in_memory_store_adapter_rewinds_list():
    """The REPL/TUI adapter mirrors the core store's revert semantics."""
    history = [{"role": "user", "content": "u1"}, {"role": "assistant", "content": "a1"}]
    store = _InMemoryConversationStore(history)
    assert store.get_messages("sid") == history
    # revert_to_message keeps messages[:index + 1] and mutates the list in place.
    store.revert_to_message("sid", 0)
    assert history == [{"role": "user", "content": "u1"}]
    store.clear_messages("sid")
    assert history == []


class _FakeAgent:
    """Minimal stand-in for the warm Agent whose chat_history grows per turn."""

    def __init__(self, chat_history):
        self.chat_history = chat_history


def test_in_memory_store_rewinds_reused_agent_chat_history():
    """The adapter also rewinds the reused agent's own chat_history boundary.

    The warm agent interleaves system/tool messages the view does not track, so
    the rewind must key off user-message count rather than a fixed offset.
    """
    view = [
        {"role": "user", "content": "u1"},
        {"role": "assistant", "content": "a1"},
        {"role": "user", "content": "u2"},
        {"role": "assistant", "content": "a2"},
    ]
    agent = _FakeAgent(
        [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "u1"},
            {"role": "assistant", "content": "a1"},
            {"role": "user", "content": "u2"},
            {"role": "tool", "content": "grep..."},
            {"role": "assistant", "content": "a2"},
        ]
    )
    store = _InMemoryConversationStore(view, agent_provider=lambda: agent)

    # Undo the last turn: keep only the first user turn in the view.
    store.revert_to_message("sid", 1)
    assert view == [
        {"role": "user", "content": "u1"},
        {"role": "assistant", "content": "a1"},
    ]
    # The agent history is rewound to the same boundary: system + first turn,
    # with the second turn's user/tool/assistant messages dropped.
    assert agent.chat_history == [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "u1"},
        {"role": "assistant", "content": "a1"},
    ]


def test_in_memory_store_clear_rewinds_agent_to_preamble():
    """Clearing the view drops all user turns from the agent, keeping preamble."""
    view = [{"role": "user", "content": "u1"}, {"role": "assistant", "content": "a1"}]
    agent = _FakeAgent(
        [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "u1"},
            {"role": "assistant", "content": "a1"},
        ]
    )
    store = _InMemoryConversationStore(view, agent_provider=lambda: agent)
    store.clear_messages("sid")
    assert view == []
    assert agent.chat_history == [{"role": "system", "content": "sys"}]


def test_in_memory_store_agent_sync_is_best_effort():
    """A missing/None agent (or one without chat_history) never raises."""
    view = [{"role": "user", "content": "u1"}, {"role": "assistant", "content": "a1"}]
    # Provider returns None (agent not built yet).
    store = _InMemoryConversationStore(view, agent_provider=lambda: None)
    store.revert_to_message("sid", 0)
    assert view == [{"role": "user", "content": "u1"}]
    # Agent without a chat_history attribute is tolerated too.
    store2 = _InMemoryConversationStore(
        [{"role": "user", "content": "u1"}], agent_provider=lambda: object()
    )
    store2.clear_messages("sid")  # must not raise


def test_repl_undo_restores_files_and_conversation(monkeypatch):
    """/undo on the default REPL path rolls files + conversation back together."""
    monkeypatch.setenv("PRAISONAI_CHECKPOINTS", "on")
    with tempfile.TemporaryDirectory() as workspace:
        monkeypatch.chdir(workspace)
        target = os.path.join(workspace, "module.py")
        _write(target, "v0\n")

        repl = InteractiveREPL(config=REPLConfig(workspace=workspace))
        repl._session_id = "test-session"

        # Build the checkpoint manager (records the session-start baseline).
        ckpt = repl._get_checkpoints()
        assert ckpt is not None and ckpt.enabled

        # A turn begins: checkpoint the boundary, then simulate the agent
        # producing a user+assistant exchange and editing the file.
        repl._checkpoint_turn("edit module")
        repl._conversation_history.append({"role": "user", "content": "edit it"})
        repl._conversation_history.append({"role": "assistant", "content": "done"})
        _write(target, "v1 rewritten\n")
        assert len(repl._conversation_history) == 2

        # /undo restores both file contents and conversation length.
        repl._handle_undo()
        with open(target) as f:
            assert f.read() == "v0\n"
        assert repl._conversation_history == []


def test_repl_revert_n_walks_back_multiple_turns(monkeypatch):
    """/revert N undoes N turns of files + conversation on the default path."""
    monkeypatch.setenv("PRAISONAI_CHECKPOINTS", "on")
    with tempfile.TemporaryDirectory() as workspace:
        monkeypatch.chdir(workspace)
        target = os.path.join(workspace, "module.py")
        _write(target, "v0\n")

        repl = InteractiveREPL(config=REPLConfig(workspace=workspace))
        repl._session_id = "test-session"
        assert repl._get_checkpoints().enabled

        # Turn 1.
        repl._checkpoint_turn("turn 1")
        repl._conversation_history.extend([
            {"role": "user", "content": "u1"},
            {"role": "assistant", "content": "a1"},
        ])
        _write(target, "v1\n")
        # Turn 2.
        repl._checkpoint_turn("turn 2")
        repl._conversation_history.extend([
            {"role": "user", "content": "u2"},
            {"role": "assistant", "content": "a2"},
        ])
        _write(target, "v2\n")

        # Revert both turns -> back to the session-start baseline.
        repl._handle_revert("2")
        with open(target) as f:
            assert f.read() == "v0\n"
        assert repl._conversation_history == []


def test_repl_undo_disabled_is_safe(monkeypatch):
    """With checkpointing off, /undo reports nothing to undo and never raises."""
    monkeypatch.setenv("PRAISONAI_CHECKPOINTS", "off")
    with tempfile.TemporaryDirectory() as workspace:
        monkeypatch.chdir(workspace)
        repl = InteractiveREPL(config=REPLConfig(workspace=workspace))
        repl._session_id = "sid"
        # Should not raise and should leave history untouched.
        repl._conversation_history.append({"role": "user", "content": "u1"})
        repl._handle_undo()
        assert repl._conversation_history == [{"role": "user", "content": "u1"}]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
