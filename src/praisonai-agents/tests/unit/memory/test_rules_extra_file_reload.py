"""Reload refreshes explicitly registered instruction files and globs."""

import pytest

from praisonaiagents.memory.rules_manager import RulesManager


@pytest.fixture
def manager(tmp_path, monkeypatch):
    monkeypatch.setattr(RulesManager, "_find_git_root", lambda self: None)
    return RulesManager(workspace_path=str(tmp_path), global_rules_path=str(tmp_path / "global"))


@pytest.mark.parametrize("absolute", [False, True])
def test_explicit_file_survives_reload_and_refreshes_content(manager, absolute):
    path = manager.workspace_path / "custom.md"
    path.write_text("Original instruction", encoding="utf-8")
    spec = str(path) if absolute else "custom.md"
    assert manager.add_rule_file(spec) == 1
    priority = manager.get_rule_by_name("custom").priority
    path.write_text("Updated instruction", encoding="utf-8")
    manager.add_rule_file(spec)
    for _ in range(2):
        manager.reload()
        assert "Updated instruction" in manager.build_rules_context()
        assert manager.get_rule_by_name("custom").priority == priority
        assert len(manager.get_all_rules()) == 1


def test_registered_glob_discovers_added_files_and_drops_removed_files(manager):
    directory = manager.workspace_path / "instructions"
    directory.mkdir()
    first = directory / "first.md"
    first.write_text("First instruction", encoding="utf-8")
    assert manager.add_rule_file("instructions/*.md") == 1
    (directory / "second.md").write_text("Second instruction", encoding="utf-8")
    first.unlink()
    manager.reload()
    assert manager.get_rule_by_name("first") is None
    assert manager.get_rule_by_name("second") is not None
    assert "Second instruction" in manager.build_rules_context()


def test_initially_empty_registered_glob_is_retried_on_reload(manager):
    assert manager.add_rule_file("instructions/*.md") == 0
    directory = manager.workspace_path / "instructions"
    directory.mkdir()
    (directory / "later.md").write_text("Later instruction", encoding="utf-8")
    manager.reload()
    assert "Later instruction" in manager.build_rules_context()


def test_automatic_rules_still_refresh_on_reload(manager):
    rule = manager.create_rule("automatic", "Original instruction")
    from pathlib import Path
    Path(rule.file_path).write_text("Updated automatic instruction", encoding="utf-8")
    manager.reload()
    assert "Updated automatic instruction" in manager.build_rules_context()
