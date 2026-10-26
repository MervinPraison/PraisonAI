"""Step-6 subdirectory walk stays inside the workspace tree (#5937)."""

import pytest

from praisonaiagents.memory.rules_manager import RulesManager


def _write_rule(directory, name, body):
    directory.mkdir(parents=True)
    (directory / f"{name}.md").write_text(
        f"---\nactivation: always\n---\n{body}\n", encoding="utf-8"
    )


@pytest.fixture(autouse=True)
def no_git_root(monkeypatch):
    monkeypatch.setattr(RulesManager, "_find_git_root", lambda self: None)


def test_cwd_outside_workspace_does_not_load_ancestor_rules(tmp_path, monkeypatch):
    outside = tmp_path / "home"
    _write_rule(outside / ".claude" / "rules", "stray", "Stray instruction")
    cwd = outside / "repo"
    cwd.mkdir()
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.chdir(cwd)

    manager = RulesManager(workspace_path=str(workspace), global_rules_path=str(tmp_path / "global"))

    assert manager.get_rule_by_name("stray") is None
    assert manager.get_active_rules() == []


def test_cwd_inside_workspace_still_loads_subdir_rules(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    nested = workspace / "pkg" / "sub"
    _write_rule(workspace / "pkg" / ".claude" / "rules", "pkgrule", "Package instruction")
    nested.mkdir(parents=True)
    _write_rule(tmp_path / ".claude" / "rules", "above", "Above workspace")
    monkeypatch.chdir(nested)

    manager = RulesManager(workspace_path=str(workspace), global_rules_path=str(tmp_path / "global"))

    assert manager.get_rule_by_name("pkgrule") is not None
    assert manager.get_rule_by_name("above") is None
