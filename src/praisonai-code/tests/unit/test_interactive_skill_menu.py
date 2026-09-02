"""Skills must surface in the interactive ``/`` menu (issue #4692).

The REPL and TUI build their command registry the same way; both previously
took ``include_skills=False``, so installed skills never appeared when a user
typed ``/``. These tests build the registry the way the REPL does, install one
skill into a temporary ``.praisonai/skills/``, and assert the skill both shows
up in the completion list and resolves to a dispatchable command.
"""

import os

import pytest

from praisonai_code.cli.interactive.command_registry import (
    CommandKind,
    create_default_registry,
)


def _install_skill(root, name: str, description: str) -> None:
    skill_dir = root / ".praisonai" / "skills" / name
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: {description}\n---\n\nBody.\n"
    )


@pytest.fixture
def in_project(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    return tmp_path


def test_skill_appears_in_completions_and_dispatches(in_project):
    _install_skill(in_project, "my-skill", "Does a useful thing")

    registry = create_default_registry(
        {"help": "Show help"}, include_custom=True, include_skills=True
    )

    assert "/my-skill" in registry.completions("/")

    command = registry.get("my-skill")
    assert command is not None
    assert command.kind is CommandKind.SKILL


def test_skill_command_dispatches_via_handler(in_project):
    """A menu entry is useless if it cannot run — the handler must yield a prompt.

    Both interactive dispatchers ignore commands whose ``handler`` is ``None``
    (they fall through to "Unknown command"). This guards the regression where
    skills were visible in ``/`` but silently un-runnable.
    """
    _install_skill(in_project, "my-skill", "Does a useful thing")

    registry = create_default_registry(
        {"help": "Show help"}, include_custom=True, include_skills=True
    )

    command = registry.get("my-skill")
    assert command is not None
    assert command.handler is not None

    prompt = command.handler("extra context")
    assert prompt
    assert "my-skill" in prompt
    assert "Does a useful thing" in prompt
    assert "Body." in prompt  # SKILL.md body is rendered into the prompt
    assert "extra context" in prompt  # user args are appended


def test_skills_omitted_by_default(in_project):
    _install_skill(in_project, "my-skill", "Does a useful thing")

    registry = create_default_registry({"help": "Show help"}, include_custom=True)

    assert "/my-skill" not in registry.completions("/")
    assert registry.get("my-skill") is None


# ---------------------------------------------------------------------------
# Through the real interactive call sites (issue #4692 follow-up)
#
# The tests above call ``create_default_registry`` directly, so they cannot
# notice if the REPL or TUI stops passing ``include_skills=True``. These go
# through ``InteractiveREPL._get_registry`` / ``AsyncTUI._get_registry``
# themselves, and also pin the ``user-invocable: false`` rule: such a skill is
# model-only and must not be offered in the ``/`` menu at all.
# ---------------------------------------------------------------------------


def _install_hidden_skill(root, name: str, description: str) -> None:
    skill_dir = root / ".praisonai" / "skills" / name
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: {description}\n"
        "user-invocable: false\n---\n\nModel-only body.\n"
    )


@pytest.fixture
def skills_project(tmp_path, monkeypatch):
    """A project with one visible skill and one ``user-invocable: false`` skill.

    ``PRAISONAI_HOME`` is pointed at a scratch dir so the developer's own
    ``~/.praisonai/skills`` and remote-skill cache cannot leak into the menu.
    """
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PRAISONAI_HOME", str(tmp_path / "home"))
    _install_skill(tmp_path, "hello", "Say hello to the user")
    _install_hidden_skill(tmp_path, "hidden", "Internal, model-only")
    return tmp_path


class _MenuIO:
    """Stand-in for the REPL's IO: records what ``_get_registry`` adds to ``/``."""

    def __init__(self):
        self.menu = {}

    def add_commands(self, commands):
        self.menu.update(commands)


def _assert_menu(registry, menu):
    # Visible skill: present in completion, lookup, and the ``/`` menu, with
    # its own description rather than a placeholder.
    assert "/hello" in registry.completions("/")
    hello = registry.get("hello")
    assert hello is not None
    assert hello.kind is CommandKind.SKILL
    assert hello.description == "Say hello to the user"
    if menu is not None:
        assert menu.get("hello") == "Say hello to the user"

    # ``user-invocable: false`` skill: absent everywhere a user could reach it.
    assert "/hidden" not in registry.completions("/")
    assert registry.get("hidden") is None
    if menu is not None:
        assert "hidden" not in menu


def test_repl_get_registry_offers_skills_and_hides_non_user_invocable(
    skills_project,
):
    from praisonai_code.cli.interactive.repl import InteractiveREPL

    io = _MenuIO()
    stub = type("StubREPL", (), {})()
    stub._registry = None
    stub.io = io

    registry = InteractiveREPL._get_registry(stub)

    assert registry is not None, "REPL registry failed to build"
    _assert_menu(registry, io.menu)


def test_tui_get_registry_offers_skills_and_hides_non_user_invocable(
    skills_project,
):
    from praisonai_code.cli.interactive.async_tui import AsyncTUI

    stub = type("StubTUI", (), {})()
    stub._registry = None
    stub._BUILTIN_COMMANDS = AsyncTUI._BUILTIN_COMMANDS  # class attr read by _get_registry

    registry = AsyncTUI._get_registry(stub)

    assert registry is not None, "TUI registry failed to build"
    _assert_menu(registry, menu=None)


def test_skill_source_skips_user_invocable_false(skills_project):
    registry = create_default_registry(
        {"help": "Show help"}, include_custom=True, include_skills=True
    )
    _assert_menu(registry, menu=None)
