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


def test_skills_omitted_by_default(in_project):
    _install_skill(in_project, "my-skill", "Does a useful thing")

    registry = create_default_registry({"help": "Show help"}, include_custom=True)

    assert "/my-skill" not in registry.completions("/")
    assert registry.get("my-skill") is None
