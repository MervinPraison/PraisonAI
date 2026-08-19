"""Tests for ecosystem-directory agent/command discovery.

Named agents and commands are discovered from the conventional ``.claude/``
and ``.agents/`` layouts in addition to ``.praisonai/`` (mirroring skills/rules
discovery), so existing project assets are reusable with zero migration.
``.praisonai/`` wins on name collision, and tools stay ``.praisonai``-only.
"""

from pathlib import Path

import pytest

from praisonai_code.cli.features.custom_definitions import (
    CustomDefinitionsDiscovery,
    count_project_tool_files,
)


AGENT_MD = "---\nrole: {role}\n---\nYou are {role}.\n"
COMMAND_MD = "---\ndescription: {desc}\n---\n{body}\n"


@pytest.fixture
def project(tmp_path, monkeypatch):
    """cwd into an empty project with the walk-up bounded to this tree."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "praisonai_code.cli.features.custom_definitions.get_git_root",
        lambda: tmp_path,
    )
    # Keep user-global discovery out of the picture.
    monkeypatch.setattr(
        CustomDefinitionsDiscovery,
        "_get_user_dir",
        lambda self: tmp_path / "no-such-user-home",
    )
    return tmp_path


def _write(base: Path, kind: str, name: str, content: str) -> None:
    d = base / kind
    d.mkdir(parents=True, exist_ok=True)
    (d / name).write_text(content)


class TestClaudeAndAgentsDiscovery:
    def test_agent_from_claude_dir(self, project):
        _write(
            project / ".claude", "agents", "reviewer.md",
            AGENT_MD.format(role="Reviewer"),
        )
        agent = CustomDefinitionsDiscovery().get_agent("reviewer")
        assert agent is not None
        assert agent.role == "Reviewer"

    def test_agent_from_agents_dir(self, project):
        _write(
            project / ".agents", "agents", "planner.md",
            AGENT_MD.format(role="Planner"),
        )
        agent = CustomDefinitionsDiscovery().get_agent("planner")
        assert agent is not None
        assert agent.role == "Planner"

    def test_command_from_claude_dir(self, project):
        _write(
            project / ".claude", "commands", "deploy.md",
            COMMAND_MD.format(desc="Deploy it", body="do $ARGUMENTS"),
        )
        cmd = CustomDefinitionsDiscovery().get_command("deploy")
        assert cmd is not None
        assert cmd.description == "Deploy it"

    def test_command_from_agents_dir(self, project):
        _write(
            project / ".agents", "commands", "lint.md",
            COMMAND_MD.format(desc="Lint it", body="lint $ARGUMENTS"),
        )
        cmd = CustomDefinitionsDiscovery().get_command("lint")
        assert cmd is not None


class TestPraisonaiPrecedence:
    def test_praisonai_agent_wins_over_claude(self, project):
        _write(
            project / ".claude", "agents", "shared.md",
            AGENT_MD.format(role="FromClaude"),
        )
        _write(
            project / ".praisonai", "agents", "shared.md",
            AGENT_MD.format(role="FromPraisonai"),
        )
        agent = CustomDefinitionsDiscovery().get_agent("shared")
        assert agent.role == "FromPraisonai"

    def test_praisonai_command_wins_over_agents(self, project):
        _write(
            project / ".agents", "commands", "shared.md",
            COMMAND_MD.format(desc="FromAgents", body="x"),
        )
        _write(
            project / ".praisonai", "commands", "shared.md",
            COMMAND_MD.format(desc="FromPraisonai", body="x"),
        )
        cmd = CustomDefinitionsDiscovery().get_command("shared")
        assert cmd.description == "FromPraisonai"


class TestAncestorWalk:
    def test_agent_discovered_from_ancestor_claude(self, project):
        # Asset lives at the repo root's .claude; cwd is a nested package.
        _write(
            project / ".claude", "agents", "root_agent.md",
            AGENT_MD.format(role="RootAgent"),
        )
        nested = project / "packages" / "web"
        nested.mkdir(parents=True)

        import os
        os.chdir(nested)

        agent = CustomDefinitionsDiscovery().get_agent("root_agent")
        assert agent is not None
        assert agent.role == "RootAgent"


class TestToolsStayPraisonaiOnly:
    def test_tools_not_loaded_from_claude(self, project, monkeypatch):
        monkeypatch.setenv("PRAISONAI_ALLOW_LOCAL_TOOLS", "true")
        _write(
            project / ".claude", "tools", "greet.py",
            "def greet(name):\n    return name\n",
        )
        discovery = CustomDefinitionsDiscovery()
        assert discovery.get_tool("greet.greet") is None

    def test_count_ignores_claude_tools(self, project, monkeypatch):
        monkeypatch.delenv("PRAISONAI_ALLOW_LOCAL_TOOLS", raising=False)
        _write(
            project / ".claude", "tools", "greet.py",
            "def greet(name):\n    return name\n",
        )
        _write(
            project / ".praisonai", "tools", "hello.py",
            "def hello(name):\n    return name\n",
        )
        # Only the .praisonai tool is counted.
        assert count_project_tool_files()[0] == 1


class TestNoEcosystemDirsUnchanged:
    def test_only_praisonai_still_works(self, project):
        _write(
            project / ".praisonai", "agents", "native.md",
            AGENT_MD.format(role="Native"),
        )
        agent = CustomDefinitionsDiscovery().get_agent("native")
        assert agent is not None
        assert agent.role == "Native"
