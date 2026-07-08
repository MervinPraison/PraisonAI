"""
Unit tests for session-lifecycle checkpointing (SessionCheckpointManager).

Validates the wrapper integration that wires the core CheckpointService into
the coding loop: auto-checkpoint per turn, /undo + /revert workspace rollback,
and default-safe disabled behaviour.
"""

import os
import tempfile

import pytest

from praisonai.cli.features.session_checkpoints import SessionCheckpointManager


def _write(path, content):
    with open(path, "w") as f:
        f.write(content)


def test_disabled_by_default_zero_overhead(monkeypatch):
    """With no config and no env override, the manager is inert."""
    monkeypatch.delenv("PRAISONAI_CHECKPOINTS", raising=False)
    with tempfile.TemporaryDirectory() as workspace:
        mgr = SessionCheckpointManager.from_config(workspace_dir=workspace)
        assert mgr.enabled is False
        assert mgr.checkpoint_turn("x") is None
        assert mgr.revert(1) is None
        assert mgr.turns == []


def test_config_auto_enables(monkeypatch):
    """checkpoints.auto: true in config enables the manager."""
    monkeypatch.delenv("PRAISONAI_CHECKPOINTS", raising=False)
    with tempfile.TemporaryDirectory() as workspace:
        mgr = SessionCheckpointManager.from_config(
            workspace_dir=workspace,
            config={"checkpoints": {"auto": True}},
        )
        assert mgr.enabled is True


def test_env_override_takes_precedence(monkeypatch):
    """PRAISONAI_CHECKPOINTS overrides config (both directions)."""
    with tempfile.TemporaryDirectory() as workspace:
        monkeypatch.setenv("PRAISONAI_CHECKPOINTS", "on")
        mgr = SessionCheckpointManager.from_config(
            workspace_dir=workspace,
            config={"checkpoints": {"auto": False}},
        )
        assert mgr.enabled is True

        monkeypatch.setenv("PRAISONAI_CHECKPOINTS", "off")
        mgr = SessionCheckpointManager.from_config(
            workspace_dir=workspace,
            config={"checkpoints": {"auto": True}},
        )
        assert mgr.enabled is False


def test_storage_dir_threaded_to_handler(monkeypatch):
    """A configured checkpoints.storage_dir reaches the underlying handler."""
    monkeypatch.delenv("PRAISONAI_CHECKPOINTS", raising=False)
    with tempfile.TemporaryDirectory() as workspace, \
            tempfile.TemporaryDirectory() as store:
        mgr = SessionCheckpointManager.from_config(
            workspace_dir=workspace,
            config={"checkpoints": {"auto": True, "storage_dir": store}},
        )
        assert mgr.storage_dir == store
        handler = mgr._get_handler()
        assert handler.storage_dir == store


def test_checkpoint_and_revert_roundtrip(monkeypatch):
    """A checkpointed turn can be rolled back, restoring file contents."""
    monkeypatch.delenv("PRAISONAI_CHECKPOINTS", raising=False)
    with tempfile.TemporaryDirectory() as workspace:
        target = os.path.join(workspace, "module.py")
        _write(target, "original\n")

        mgr = SessionCheckpointManager.from_config(
            workspace_dir=workspace,
            config={"checkpoints": {"auto": True}},
        )

        # Session-start baseline captures the original file.
        assert mgr.checkpoint_turn("session start") is not None

        # Agent mutates the file on the next turn (checkpoint taken first).
        assert mgr.checkpoint_turn("refactor") is not None
        _write(target, "rewritten by agent\n")

        # Revert one turn -> workspace restored to the pre-refactor state.
        restored = mgr.revert(1)
        assert restored is not None
        with open(target) as f:
            assert f.read() == "original\n"


def test_sequential_revert_walks_back_history(monkeypatch):
    """Repeated revert(1) walks the timeline back instead of pinning one turn."""
    monkeypatch.delenv("PRAISONAI_CHECKPOINTS", raising=False)
    with tempfile.TemporaryDirectory() as workspace:
        target = os.path.join(workspace, "module.py")
        _write(target, "v0\n")

        mgr = SessionCheckpointManager.from_config(
            workspace_dir=workspace,
            config={"checkpoints": {"auto": True}},
        )

        # Turn 1 checkpoint captures v0, then file becomes v1.
        assert mgr.checkpoint_turn("turn 1") is not None
        _write(target, "v1\n")
        # Turn 2 checkpoint captures v1, then file becomes v2.
        assert mgr.checkpoint_turn("turn 2") is not None
        _write(target, "v2\n")

        assert len(mgr.turns) == 2

        # First revert restores turn 2's checkpoint (v1) and drops it.
        first = mgr.revert(1)
        assert first is not None
        assert len(mgr.turns) == 1
        with open(target) as f:
            assert f.read() == "v1\n"

        # Second revert must walk further back to turn 1's checkpoint (v0),
        # not restore the same checkpoint again.
        second = mgr.revert(1)
        assert second is not None
        assert len(mgr.turns) == 0
        with open(target) as f:
            assert f.read() == "v0\n"


def test_revert_out_of_range_is_safe(monkeypatch):
    """Reverting more turns than exist returns None without raising."""
    monkeypatch.delenv("PRAISONAI_CHECKPOINTS", raising=False)
    with tempfile.TemporaryDirectory() as workspace:
        _write(os.path.join(workspace, "a.txt"), "a\n")
        mgr = SessionCheckpointManager.from_config(
            workspace_dir=workspace,
            config={"checkpoints": {"auto": True}},
        )
        mgr.checkpoint_turn("session start")
        assert mgr.revert(5) is None


class _FakeConversationStore:
    """Minimal stand-in for HierarchicalSessionStore's revert surface."""

    def __init__(self, messages):
        self.messages = list(messages)

    def get_messages(self, session_id):
        return list(self.messages)

    def revert_to_message(self, session_id, message_index):
        # Mirror core HierarchicalSessionStore semantics exactly: keep
        # messages[:index + 1], and reject out-of-range indices (return False).
        if message_index < 0 or message_index >= len(self.messages):
            return False
        self.messages = self.messages[: message_index + 1]
        return True

    def clear_messages(self, session_id):
        self.messages = []
        return True


def test_revert_rewinds_conversation_history(monkeypatch):
    """revert(n) rewinds conversation history to the captured turn boundary."""
    monkeypatch.delenv("PRAISONAI_CHECKPOINTS", raising=False)
    with tempfile.TemporaryDirectory() as workspace:
        target = os.path.join(workspace, "module.py")
        _write(target, "v0\n")

        store = _FakeConversationStore(["u1", "a1"])  # 2 messages before turn
        mgr = SessionCheckpointManager.from_config(
            workspace_dir=workspace,
            config={"checkpoints": {"auto": True}},
            session_store=store,
            session_id="sid",
        )

        # Turn checkpoint captures both files (v0) and message_count (2).
        assert mgr.checkpoint_turn("refactor") is not None
        _write(target, "v1\n")
        # The turn appended new assistant/tool messages.
        store.messages.extend(["a2_tool", "a2_final"])
        assert len(store.messages) == 4

        restored = mgr.revert(1)
        assert restored is not None
        # Files rolled back.
        with open(target) as f:
            assert f.read() == "v0\n"
        # Conversation history rolled back to the 2-message boundary.
        assert store.messages == ["u1", "a1"]


def test_dropped_message_count_reports_pending_rollback(monkeypatch):
    """preview surfaces how many messages a revert would drop."""
    monkeypatch.delenv("PRAISONAI_CHECKPOINTS", raising=False)
    with tempfile.TemporaryDirectory() as workspace:
        _write(os.path.join(workspace, "a.txt"), "a\n")
        store = _FakeConversationStore(["u1"])
        mgr = SessionCheckpointManager.from_config(
            workspace_dir=workspace,
            config={"checkpoints": {"auto": True}},
            session_store=store,
            session_id="sid",
        )
        assert mgr.checkpoint_turn("turn 1") is not None
        store.messages.extend(["a1", "a1_tool"])
        assert mgr.dropped_message_count(1) == 2


def test_revert_to_zero_message_boundary_clears_history(monkeypatch):
    """Undoing a turn checkpointed before any messages clears history to empty.

    Guards the off-by-one where targeting index 0 via revert_to_message would
    keep the first message: at a 0-message boundary we must clear, not truncate.
    """
    monkeypatch.delenv("PRAISONAI_CHECKPOINTS", raising=False)
    with tempfile.TemporaryDirectory() as workspace:
        target = os.path.join(workspace, "module.py")
        _write(target, "v0\n")

        # Empty conversation at checkpoint time -> message_count captured as 0.
        store = _FakeConversationStore([])
        mgr = SessionCheckpointManager.from_config(
            workspace_dir=workspace,
            config={"checkpoints": {"auto": True}},
            session_store=store,
            session_id="sid",
        )

        assert mgr.checkpoint_turn("first turn") is not None
        _write(target, "v1\n")
        # The turn produced the very first conversation messages.
        store.messages.extend(["u1", "a1", "a1_tool"])

        restored = mgr.revert(1)
        assert restored is not None
        with open(target) as f:
            assert f.read() == "v0\n"
        # History rolls back to the empty boundary — no ghost first message.
        assert store.messages == []


def test_revert_to_zero_boundary_without_clear_is_noop(monkeypatch):
    """A store lacking a clear primitive must not leave a stale first message.

    The old code called revert_to_message(session_id, 0) which, under real core
    semantics, keeps messages[:1]. Absent an explicit clear method we now no-op
    rather than corrupt history with a ghost message.
    """
    monkeypatch.delenv("PRAISONAI_CHECKPOINTS", raising=False)

    class _NoClearStore:
        def __init__(self, messages):
            self.messages = list(messages)

        def get_messages(self, session_id):
            return list(self.messages)

        def revert_to_message(self, session_id, message_index):
            if message_index < 0 or message_index >= len(self.messages):
                return False
            self.messages = self.messages[: message_index + 1]
            return True

    with tempfile.TemporaryDirectory() as workspace:
        target = os.path.join(workspace, "module.py")
        _write(target, "v0\n")

        store = _NoClearStore([])
        mgr = SessionCheckpointManager.from_config(
            workspace_dir=workspace,
            config={"checkpoints": {"auto": True}},
            session_store=store,
            session_id="sid",
        )

        assert mgr.checkpoint_turn("first turn") is not None
        _write(target, "v1\n")
        store.messages.extend(["u1", "a1"])

        restored = mgr.revert(1)
        assert restored is not None
        with open(target) as f:
            assert f.read() == "v0\n"
        # No ghost message: without a clear primitive we leave history untouched
        # rather than truncating to messages[:1] via the buggy index-0 path.
        assert store.messages == ["u1", "a1"]


def test_no_session_store_is_file_only(monkeypatch):
    """Without a conversation store, behaviour is unchanged (file-only)."""
    monkeypatch.delenv("PRAISONAI_CHECKPOINTS", raising=False)
    with tempfile.TemporaryDirectory() as workspace:
        target = os.path.join(workspace, "module.py")
        _write(target, "v0\n")
        mgr = SessionCheckpointManager.from_config(
            workspace_dir=workspace,
            config={"checkpoints": {"auto": True}},
        )
        assert mgr.checkpoint_turn("turn 1") is not None
        _write(target, "v1\n")
        assert mgr.dropped_message_count(1) is None
        restored = mgr.revert(1)
        assert restored is not None
        with open(target) as f:
            assert f.read() == "v0\n"


def test_standalone_checkpoint_command_honors_configured_storage_dir(monkeypatch):
    """`praisonai checkpoint` reads the same store as `code --checkpoints`.

    Guards against the split-store regression where the standalone command
    group built CheckpointsHandler without the configured storage_dir and so
    reported saved checkpoints as missing.
    """
    from praisonai.cli.commands import checkpoint as checkpoint_cmd

    with tempfile.TemporaryDirectory() as workspace, \
            tempfile.TemporaryDirectory() as store:
        class _Cfg:
            extra = {"checkpoints": {"auto": True, "storage_dir": store}}

        monkeypatch.setattr(
            "praisonai.cli.configuration.resolver.resolve_config",
            lambda *a, **k: _Cfg(),
        )

        handler = checkpoint_cmd._handler(workspace=workspace)
        assert handler.storage_dir == store


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
