"""Public rule loading resolves documented home-directory imports."""

from pathlib import Path

import pytest

from praisonaiagents.memory.rules_manager import RulesManager


@pytest.fixture
def rule_paths(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    home = tmp_path / "home"
    workspace.mkdir()
    (home / "shared").mkdir(parents=True)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    monkeypatch.setattr(RulesManager, "_find_git_root", lambda self: None)
    return workspace, home, tmp_path / "global"


@pytest.mark.parametrize("reference", ["@~/shared/rule.md", "@~/shared/rule"])
def test_home_import_is_in_public_context(rule_paths, reference):
    workspace, home, global_path = rule_paths
    (home / "shared" / "rule.md").write_text("Shared instruction", encoding="utf-8")
    (workspace / "PRAISON.md").write_text(reference, encoding="utf-8")
    manager = RulesManager(workspace_path=str(workspace), global_rules_path=str(global_path))
    context = manager.build_rules_context()
    assert "Shared instruction" in context
    assert reference not in context


def test_home_import_resolves_nested_file_relative_import(rule_paths):
    workspace, home, global_path = rule_paths
    (home / "shared" / "rule.md").write_text("@./nested.md", encoding="utf-8")
    (home / "shared" / "nested.md").write_text("Nested instruction", encoding="utf-8")
    (workspace / "PRAISON.md").write_text("@~/shared/rule.md", encoding="utf-8")
    manager = RulesManager(workspace_path=str(workspace), global_rules_path=str(global_path))
    assert "Nested instruction" in manager.build_rules_context()


@pytest.mark.parametrize("reference", ["@local.md", "@./local.md"])
def test_workspace_and_file_relative_controls(rule_paths, reference):
    workspace, home, global_path = rule_paths
    (workspace / "local.md").write_text("Local instruction", encoding="utf-8")
    (workspace / "PRAISON.md").write_text(reference, encoding="utf-8")
    manager = RulesManager(workspace_path=str(workspace), global_rules_path=str(global_path))
    assert "Local instruction" in manager.build_rules_context()


def test_unresolved_reference_and_mention_are_preserved(rule_paths):
    workspace, home, global_path = rule_paths
    text = "@~/shared/missing.md @reviewer"
    (workspace / "PRAISON.md").write_text(text, encoding="utf-8")
    manager = RulesManager(workspace_path=str(workspace), global_rules_path=str(global_path))
    assert text in manager.build_rules_context()
