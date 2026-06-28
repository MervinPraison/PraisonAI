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


def test_disabled_by_default_zero_overhead():
    """With no config and no env override, the manager is inert."""
    os.environ.pop("PRAISONAI_CHECKPOINTS", None)
    with tempfile.TemporaryDirectory() as workspace:
        mgr = SessionCheckpointManager.from_config(workspace_dir=workspace)
        assert mgr.enabled is False
        assert mgr.checkpoint_turn("x") is None
        assert mgr.revert(1) is None
        assert mgr.turns == []


def test_config_auto_enables():
    """checkpoints.auto: true in config enables the manager."""
    os.environ.pop("PRAISONAI_CHECKPOINTS", None)
    with tempfile.TemporaryDirectory() as workspace:
        mgr = SessionCheckpointManager.from_config(
            workspace_dir=workspace,
            config={"checkpoints": {"auto": True}},
        )
        assert mgr.enabled is True


def test_env_override_takes_precedence():
    """PRAISONAI_CHECKPOINTS overrides config (both directions)."""
    with tempfile.TemporaryDirectory() as workspace:
        os.environ["PRAISONAI_CHECKPOINTS"] = "on"
        try:
            mgr = SessionCheckpointManager.from_config(
                workspace_dir=workspace,
                config={"checkpoints": {"auto": False}},
            )
            assert mgr.enabled is True

            os.environ["PRAISONAI_CHECKPOINTS"] = "off"
            mgr = SessionCheckpointManager.from_config(
                workspace_dir=workspace,
                config={"checkpoints": {"auto": True}},
            )
            assert mgr.enabled is False
        finally:
            os.environ.pop("PRAISONAI_CHECKPOINTS", None)


def test_checkpoint_and_revert_roundtrip():
    """A checkpointed turn can be rolled back, restoring file contents."""
    os.environ.pop("PRAISONAI_CHECKPOINTS", None)
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


def test_revert_out_of_range_is_safe():
    """Reverting more turns than exist returns None without raising."""
    os.environ.pop("PRAISONAI_CHECKPOINTS", None)
    with tempfile.TemporaryDirectory() as workspace:
        _write(os.path.join(workspace, "a.txt"), "a\n")
        mgr = SessionCheckpointManager.from_config(
            workspace_dir=workspace,
            config={"checkpoints": {"auto": True}},
        )
        mgr.checkpoint_turn("session start")
        assert mgr.revert(5) is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
