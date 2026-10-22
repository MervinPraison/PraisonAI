"""RulesManager step-6 CWD walk stays within workspace / git-root tree."""

from pathlib import Path

import pytest

from praisonaiagents.memory.rules_manager import RulesManager


@pytest.fixture
def manager_factory(tmp_path, monkeypatch):
    monkeypatch.setattr(RulesManager, "_find_git_root", lambda self: None)
    global_path = tmp_path / "global"
    global_path.mkdir()

    def _make(workspace: Path) -> RulesManager:
        return RulesManager(
            workspace_path=str(workspace),
            global_rules_path=str(global_path),
        )

    return _make


def test_reload_skips_ancestor_walk_when_cwd_outside_workspace(
    tmp_path, monkeypatch, manager_factory
):
    """CWD above workspace must not walk ancestors (would ingest unrelated .claude/rules)."""
    claude_rules = tmp_path / ".claude" / "rules"
    claude_rules.mkdir(parents=True)
    (claude_rules / "probe.md").write_text(
        "---\nactivation: always\n---\nOutside workspace", encoding="utf-8"
    )
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.chdir(tmp_path)
    manager = manager_factory(workspace)
    manager.reload()
    assert manager.get_rule_by_name("probe") is None


def test_reload_discovers_subdir_rules_when_cwd_inside_workspace(
    tmp_path, monkeypatch, manager_factory
):
    workspace = tmp_path / "workspace"
    nested = workspace / "pkg" / "sub"
    rules_dir = nested / ".claude" / "rules"
    rules_dir.mkdir(parents=True)
    (rules_dir / "nested.md").write_text(
        "---\nactivation: always\n---\nNested", encoding="utf-8"
    )
    monkeypatch.chdir(nested)
    manager = manager_factory(workspace)
    manager.reload()
    assert manager.get_rule_by_name("nested") is not None
