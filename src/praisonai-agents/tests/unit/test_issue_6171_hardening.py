"""Regression tests for issue #6171.

1. Agent.output_file must not overwrite a hardlinked file outside the root.
2. Shadow-git / worktree git calls are bounded by a timeout and non-interactive.
3. A torn learn-store archive is quarantined and eviction keeps working.
"""

import os
import subprocess
from unittest import mock

import pytest


def test_agent_output_file_hardlink_does_not_touch_outside_inode(tmp_path, monkeypatch):
    from praisonaiagents import Agent, OutputConfig

    root = tmp_path / "root"
    root.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("SECRET")
    link = root / "out.md"
    try:
        os.link(outside, link)
    except (OSError, NotImplementedError):
        pytest.skip("hardlinks unsupported")

    monkeypatch.setenv("PRAISONAI_PROJECT_ROOT", str(root))
    monkeypatch.chdir(root)
    agent = Agent(name="writer", output=OutputConfig(output_file="out.md"))
    assert agent._save_output_to_file("AGENT-OVERWRITE") is True

    assert outside.read_text() == "SECRET"
    assert link.read_text() == "AGENT-OVERWRITE"


def test_agent_output_file_outside_root_rejected(tmp_path, monkeypatch):
    from praisonaiagents import Agent, OutputConfig

    root = tmp_path / "root"
    root.mkdir()
    monkeypatch.setenv("PRAISONAI_PROJECT_ROOT", str(root))
    agent = Agent(name="writer", output=OutputConfig(output_file=str(tmp_path / "escape.md")))
    assert agent._save_output_to_file("x") is False
    assert not (tmp_path / "escape.md").exists()


def test_snapshot_run_git_is_bounded_and_non_interactive(tmp_path):
    from praisonaiagents.snapshot import snapshot as snap_mod

    fs = snap_mod.FileSnapshot(str(tmp_path), snapshot_dir=str(tmp_path / "snaps"))
    with mock.patch.object(
        snap_mod.subprocess, "run",
        side_effect=subprocess.TimeoutExpired(["git"], snap_mod._GIT_TIMEOUT),
    ) as run:
        with pytest.raises(subprocess.TimeoutExpired):
            fs._run_git("status")
    kwargs = run.call_args.kwargs
    assert kwargs["timeout"] == snap_mod._GIT_TIMEOUT
    assert kwargs["env"]["GIT_TERMINAL_PROMPT"] == "0"


def test_git_worktree_timeout_treated_as_unavailable(tmp_path):
    from praisonaiagents.workspace.adapters import git_worktree as gw

    with mock.patch(
        "subprocess.run",
        side_effect=subprocess.TimeoutExpired(["git"], gw._GIT_TIMEOUT),
    ) as run:
        adapter = gw.GitWorktreeAdapter(tmp_path)
    assert adapter.available is False
    kwargs = run.call_args.kwargs
    assert kwargs["timeout"] == gw._GIT_TIMEOUT
    assert kwargs["env"]["GIT_TERMINAL_PROMPT"] == "0"


def test_corrupt_archive_quarantined_and_eviction_continues(tmp_path):
    from praisonaiagents.memory.learn.stores import InsightStore

    st = InsightStore(store_path=str(tmp_path / "insights.json"), max_entries=3)
    for i in range(5):
        st.add(f"insight {i}")
    archive = st._archive_path()
    archive.write_text('[{"id": "x", "cont')  # torn write

    for i in range(5, 12):
        st.add(f"insight {i}")

    assert len(st._entries) == 3
    sidecars = list(tmp_path.glob("insights.archive.json.*.corrupt"))
    assert sidecars and sidecars[0].read_text() == '[{"id": "x", "cont'
    import json
    assert isinstance(json.loads(archive.read_text()), list)
