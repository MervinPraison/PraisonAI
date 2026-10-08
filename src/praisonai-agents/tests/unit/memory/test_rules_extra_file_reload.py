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


def test_latest_registration_keeps_named_lookup_precedence_after_reload(manager):
    for directory, content in (("a", "From A"), ("b", "From B")):
        path = manager.workspace_path / directory
        path.mkdir()
        (path / "custom.md").write_text(content, encoding="utf-8")
    for spec in ("a/custom.md", "b/custom.md", "a/custom.md"):
        assert manager.add_rule_file(spec) == 1
    assert manager.get_rule_by_name("custom").content == "From A"
    for _ in range(2):
        manager.reload()
        assert manager.get_rule_by_name("custom").content == "From A"
        assert len(manager._extra_rule_files) == 2


@pytest.mark.parametrize("scope", ["workspace", "global", "subdir"])
def test_latest_registration_wins_over_registered_discovered_scope(manager, monkeypatch, scope):
    if scope == "subdir":
        directory = manager.workspace_path / "child"
        path = directory / manager.RULES_DIR_NAME / "custom.md"
        path.parent.mkdir(parents=True)
        path.write_text("Discovered instruction", encoding="utf-8")
        monkeypatch.chdir(directory)
        manager.reload()
        discovered = manager.get_rule_by_name("custom")
    else:
        discovered = manager.create_rule("custom", "Discovered instruction", scope=scope)
    explicit = manager.workspace_path / "instructions" / "custom.md"
    explicit.parent.mkdir()
    explicit.write_text("Latest explicit instruction", encoding="utf-8")
    assert manager.add_rule_file(discovered.file_path) == 1
    assert manager.add_rule_file(str(explicit)) == 1
    for _ in range(2):
        assert manager.get_rule_by_name("custom").content == "Latest explicit instruction"
        context = manager.build_rules_context()
        assert "Discovered instruction" in context
        assert "Latest explicit instruction" in context
        # Keeping discovery keys must preserve the public deletion scope.
        assert f"{scope}:custom" in manager._rules
        manager.reload()


@pytest.mark.parametrize("source", ["root", "workspace"])
def test_registered_auto_discovered_file_is_in_context_once(manager, source):
    path = manager.workspace_path / "AGENTS.md" if source == "root" else manager.workspace_path / manager.RULES_DIR_NAME / "custom.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("Unique instruction marker", encoding="utf-8")
    manager.reload()
    assert manager.add_rule_file(str(path)) == 1
    for _ in range(2):
        assert manager.build_rules_context().count("Unique instruction marker") == 1
        assert len(manager.get_all_rules()) == 1
        manager.reload()


def test_same_named_glob_matches_are_all_retained(manager):
    for directory, content in (("a", "Unique A"), ("b", "Unique B")):
        path = manager.workspace_path / "instructions" / directory
        path.mkdir(parents=True)
        (path / "rules.md").write_text(content, encoding="utf-8")
    assert manager.add_rule_file("instructions/*/rules.md") == 2
    for _ in range(2):
        assert len(manager.get_all_rules()) == 2
        context = manager.build_rules_context()
        assert context.count("Unique A") == context.count("Unique B") == 1
        manager.reload()


def test_same_named_glob_rules_reach_path_scoped_prompt(manager, monkeypatch):
    from praisonaiagents import Agent

    for directory, content in (("a", "GLOB_A_MARKER"), ("b", "GLOB_B_MARKER")):
        path = manager.workspace_path / "instructions" / directory
        path.mkdir(parents=True)
        (path / "rules.md").write_text(
            f'---\nglobs: ["*.py"]\nactivation: glob\n---\n{content}', encoding="utf-8"
        )
    assert manager.add_rule_file("instructions/*/rules.md") == 2
    agent = Agent(name="test", llm="gpt-4o-mini")
    agent._rules_manager = manager
    agent._rules_manager_initialized = True
    monkeypatch.setattr(agent, "_collect_touched_file_paths", lambda: ["foo.py", "bar.py"])
    for _ in range(2):
        matched = manager.get_glob_rules_for_paths(["foo.py", "bar.py", "foo.py"])
        assert len(matched) == 2
        assert manager.get_glob_rules_for_paths(["foo.py"], exclude_names={"rules"}) == []
        prompt = agent._append_glob_rules_context("Base prompt")
        assert prompt.count("GLOB_A_MARKER") == prompt.count("GLOB_B_MARKER") == 1
        manager.reload()


@pytest.mark.parametrize("rule_scope,delete_scope", [
    ("workspace", "workspace"), ("workspace", None), ("global", "global"), ("global", None),
])
def test_registered_discovered_rule_remains_deletable(manager, rule_scope, delete_scope):
    from pathlib import Path

    rule = manager.create_rule("custom", "Scoped instruction", scope=rule_scope)
    path = Path(rule.file_path)
    assert manager.add_rule_file(str(path)) == 1
    manager.reload()
    assert manager.delete_rule("custom", scope=delete_scope)
    assert not path.exists()
    assert manager.get_all_rules() == []
    manager.reload()
    assert manager.get_all_rules() == []


def test_explicit_workspace_registration_does_not_grant_global_deletion(manager):
    from pathlib import Path

    rule = manager.create_rule("custom", "Scoped instruction")
    assert manager.add_rule_file(rule.file_path) == 1
    assert not manager.delete_rule("custom", scope="global")
    assert Path(rule.file_path).exists()
    assert "Scoped instruction" in manager.build_rules_context()


@pytest.mark.parametrize("scope", ["workspace", "global"])
def test_deleted_registered_rule_recreation_does_not_steal_precedence(manager, scope):
    """Only a live explicit registration participates in immediate lookup."""
    original = manager.create_rule("custom", "Old scoped", scope=scope)
    other = manager.workspace_path / "custom.md"
    other.write_text("Latest explicit", encoding="utf-8")
    assert manager.add_rule_file(original.file_path) == 1
    assert manager.add_rule_file(str(other)) == 1
    assert manager.delete_rule("custom", scope=scope)
    manager.create_rule("custom", "Recreated automatic", scope=scope)
    assert manager.get_rule_by_name("custom").content == "Latest explicit"


def test_overlapping_specs_and_path_spellings_share_one_rule(manager):
    directory = manager.workspace_path / "instructions"
    directory.mkdir()
    path = directory / "custom.md"
    path.write_text("Shared instruction marker", encoding="utf-8")
    for spec in ("instructions/custom.md", str(path), "instructions/*.md"):
        assert manager.add_rule_file(spec) == 1
    priority = manager.get_all_rules()[0].priority
    for _ in range(2):
        manager.reload()
        assert len(manager.get_all_rules()) == 1
        assert manager.get_all_rules()[0].priority == priority
        assert manager.build_rules_context().count("Shared instruction marker") == 1


@pytest.mark.parametrize("spec", ["instructions/*.md", "instructions/later.md", None])
def test_agent_keeps_initially_empty_explicit_registration(tmp_path, monkeypatch, spec):
    from praisonaiagents import Agent
    from praisonaiagents.config.feature_configs import RulesConfig

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(RulesManager, "_find_git_root", lambda self: None)
    original_init = RulesManager.__init__

    def isolated_init(self, **kwargs):
        kwargs["global_rules_path"] = str(tmp_path / "global")
        original_init(self, **kwargs)

    monkeypatch.setattr(RulesManager, "__init__", isolated_init)
    agent = Agent(name="test", llm="gpt-4o-mini", rules=RulesConfig(
        workspace_path=str(tmp_path), files=[spec] if spec else []
    ))
    manager = agent.rules_manager
    if spec is None:
        assert manager is None
        assert agent.get_rules_context() == ""
        return
    assert manager is not None
    assert agent.get_rules_context() == ""
    directory = tmp_path / "instructions"
    directory.mkdir()
    (directory / "later.md").write_text("Later instruction marker", encoding="utf-8")
    manager.reload()
    assert "Later instruction marker" in agent.get_rules_context()
