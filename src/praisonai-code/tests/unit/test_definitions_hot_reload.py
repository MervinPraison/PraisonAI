"""File-based definitions are hot-reloaded in long-lived sessions (Issue #5812).

Editing commands/skills/rules/tools under a known definition root must take
effect on the next prompt in an interactive session or the warm runtime,
without a restart.
"""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from praisonai_code.cli.features import custom_definitions
from praisonai_code.cli.features.custom_definitions import definitions_fingerprint
from praisonai_code.cli.interactive.command_registry import create_default_registry
from praisonai_code.runtime.server import WarmRuntime


@pytest.fixture
def project(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    proj = tmp_path / "proj"
    proj.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    monkeypatch.chdir(proj)
    monkeypatch.setattr(custom_definitions, "_FINGERPRINT_TTL", 0)
    return proj


def _write_command(proj: Path, name: str, description: str) -> Path:
    cmd_dir = proj / ".praisonai" / "commands"
    cmd_dir.mkdir(parents=True, exist_ok=True)
    path = cmd_dir / f"{name}.md"
    path.write_text(f"---\ndescription: {description}\n---\nDo {name}: $ARGUMENTS\n")
    return path


def _bump_mtime(path: Path) -> None:
    st = path.stat()
    os.utime(path, ns=(st.st_atime_ns, st.st_mtime_ns + 10_000_000_000))


def test_fingerprint_changes_on_add_edit_and_rules(project):
    before = definitions_fingerprint()
    path = _write_command(project, "foo", "Foo")
    added = definitions_fingerprint()
    assert added != before

    _bump_mtime(path)
    assert definitions_fingerprint() != added

    edited = definitions_fingerprint()
    (project / "AGENTS.md").write_text("Always be terse.\n")
    assert definitions_fingerprint() != edited


def test_fingerprint_is_cached_within_ttl(project, monkeypatch):
    monkeypatch.setattr(custom_definitions, "_FINGERPRINT_TTL", 60)
    first = definitions_fingerprint()
    _write_command(project, "foo", "Foo")
    assert definitions_fingerprint() == first


def test_new_custom_command_resolves_without_restart(project):
    registry = create_default_registry(
        {"help": "Show help"}, include_custom=True, discover_entry_points=False
    )
    assert registry.get("foo") is None

    _write_command(project, "foo", "Foo command")
    command = registry.get("foo")
    assert command is not None
    assert command.description == "Foo command"


def test_edited_custom_command_description_refreshes(project):
    path = _write_command(project, "foo", "Old")
    registry = create_default_registry(include_custom=True, discover_entry_points=False)
    assert registry.get("foo").description == "Old"

    path.write_text("---\ndescription: New\n---\nbody\n")
    _bump_mtime(path)
    assert registry.get("foo").description == "New"


def test_removed_custom_command_disappears(project):
    path = _write_command(project, "foo", "Foo")
    registry = create_default_registry(include_custom=True, discover_entry_points=False)
    assert registry.has("foo")

    path.unlink()
    assert not registry.has("foo")


class _FakeAgent:
    def __init__(self, **kwargs):
        self.chat_history = []

    def start(self, prompt):
        return f"re: {prompt}"

    def _replace_chat_history(self, new_history):
        self.chat_history = list(new_history)


def test_warm_runtime_rebuilds_agents_after_rules_edit(project):
    runtime = WarmRuntime(model="test-model")
    with patch("praisonaiagents.Agent", _FakeAgent), patch(
        "praisonai_code.cli.state.project_sessions.apply_cli_session_continuity",
        lambda *a, **k: None,
    ), patch("praisonai_code.runtime.server._apply_cold_path_parity", lambda c: None):
        runtime.run("one")
        runtime.run("one", session_id="s1")
        anon = runtime._agents["test-model"]
        session = runtime._session_agents["s1"]

        # Unchanged definitions: warm agents are reused.
        runtime.run("two")
        runtime.run("two", session_id="s1")
        assert runtime._agents["test-model"] is anon
        assert runtime._session_agents["s1"] is session

        (project / "AGENTS.md").write_text("New rule.\n")
        runtime.run("three")
        runtime.run("three", session_id="s1")
        assert runtime._agents["test-model"] is not anon
        assert runtime._session_agents["s1"] is not session


def test_fingerprint_watches_workspace_outside_cwd(project, tmp_path):
    workspace = tmp_path / "other"
    workspace.mkdir()
    before = definitions_fingerprint(str(workspace))
    (workspace / "AGENTS.md").write_text("Workspace rule.\n")
    assert definitions_fingerprint(str(workspace)) != before


def test_fingerprint_watches_lowercase_skill_md_and_praisonai_home(project, tmp_path, monkeypatch):
    skill = project / ".claude" / "skills" / "demo"
    skill.mkdir(parents=True)
    skill_md = skill / "skill.md"
    skill_md.write_text("---\nname: demo\ndescription: Old\n---\nbody\n")
    before = definitions_fingerprint()
    _bump_mtime(skill_md)
    assert definitions_fingerprint() != before

    praison_home = tmp_path / "praison_home"
    monkeypatch.setenv("PRAISONAI_HOME", str(praison_home))
    (praison_home / "skills").mkdir(parents=True)
    before = definitions_fingerprint()
    (praison_home / "skills" / "user-skill").mkdir()
    assert definitions_fingerprint() != before


def test_subtree_attacher_reattaches_edited_nested_instructions(tmp_path):
    from praisonai_code.integration.context_files import PathContextAttacher

    pkg = tmp_path / "packages" / "foo"
    pkg.mkdir(parents=True)
    rules = pkg / "AGENTS.md"
    rules.write_text("Old package rule.\n")
    target = pkg / "mod.py"
    target.write_text("")

    attacher = PathContextAttacher(max_chars=0)
    assert "Old package rule." in attacher.attach_for_path(target)
    # Unchanged: cached result is reused.
    assert "Old package rule." in attacher.attach_for_path(target)

    rules.write_text("New package rule.\n")
    _bump_mtime(rules)
    assert "New package rule." in attacher.attach_for_path(target)


def test_warm_session_rebuild_restores_history_from_store(project, tmp_path, monkeypatch):
    monkeypatch.setenv("PRAISONAI_HOME", str(tmp_path / "praison_home"))
    from praisonai_code.cli.state.project_sessions import get_project_session_store

    store = get_project_session_store()
    store.add_user_message("s1", "remember 42")
    store.add_assistant_message("s1", "noted")

    runtime = WarmRuntime(model="test-model")
    with patch("praisonaiagents.Agent", _FakeAgent), patch(
        "praisonai_code.runtime.server._apply_cold_path_parity", lambda c: None
    ):
        first = runtime._get_session_agent("s1", None)
        (project / "AGENTS.md").write_text("New rule.\n")
        runtime._refresh_if_definitions_changed()
        rebuilt = runtime._get_session_agent("s1", None)

    assert rebuilt is not first
    contents = [m["content"] for m in rebuilt.chat_history]
    assert contents[:2] == ["remember 42", "noted"]
