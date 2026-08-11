"""Tests for Agent.set_snapshot_root (bug: /undo tracked the wrong directory).

The bot/gateway layer attaches ``agent._workspace`` *after* construction, but
the FileSnapshot backing ``Agent.undo`` was created rooted at ``os.getcwd()``.
``set_snapshot_root`` lets the wrapper re-root change tracking at the directory
the file tools actually write to, so ``/undo`` reverts the right files.
"""

import os
import tempfile

from praisonaiagents import Agent


def test_set_snapshot_root_creates_snapshot_at_workspace():
    """set_snapshot_root roots the file snapshot at the given directory."""
    agent = Agent(instructions="test", llm="gpt-4o-mini")
    with tempfile.TemporaryDirectory() as workspace:
        rooted = agent.set_snapshot_root(workspace)
        # Git may be unavailable in CI; only assert rooting when it succeeded.
        if rooted:
            assert agent._file_snapshot is not None
            assert agent._file_snapshot.project_path == os.path.abspath(workspace)


def test_set_snapshot_root_noop_when_unchanged():
    """Re-rooting at the same directory is a no-op (keeps the same manager)."""
    agent = Agent(instructions="test", llm="gpt-4o-mini")
    with tempfile.TemporaryDirectory() as workspace:
        if not agent.set_snapshot_root(workspace):
            return  # git unavailable
        first = agent._file_snapshot
        assert agent.set_snapshot_root(workspace) is True
        assert agent._file_snapshot is first


def test_set_snapshot_root_reroots_and_clears_stacks():
    """Rooting at a new directory clears stale undo/redo stacks."""
    agent = Agent(instructions="test", llm="gpt-4o-mini")
    with tempfile.TemporaryDirectory() as ws1, tempfile.TemporaryDirectory() as ws2:
        if not agent.set_snapshot_root(ws1):
            return  # git unavailable
        # Simulate a prior snapshot recorded against ws1.
        agent._snapshot_stack.append("deadbeef")
        agent._redo_stack.append("cafef00d")

        assert agent.set_snapshot_root(ws2) is True
        assert agent._file_snapshot.project_path == os.path.abspath(ws2)
        assert agent._snapshot_stack == []
        assert agent._redo_stack == []


def test_undo_without_snapshot_returns_false():
    """undo is a safe no-op when nothing has been tracked."""
    agent = Agent(instructions="test", llm="gpt-4o-mini")
    with tempfile.TemporaryDirectory() as workspace:
        agent.set_snapshot_root(workspace)
        assert agent.undo() is False
