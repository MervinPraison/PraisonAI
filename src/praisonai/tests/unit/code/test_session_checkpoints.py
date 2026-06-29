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
