"""Tests for zero-ceremony project-local tool discovery.

Covers the wrapper convention that auto-loads ``.praisonai/tools/*.py`` on
``praisonai run``, mirroring the existing ``agents/`` and ``commands/``
discovery. Loading is gated by ``PRAISONAI_ALLOW_LOCAL_TOOLS``.
"""

from pathlib import Path

import pytest

from praisonai_code.cli.features.custom_definitions import (
    CustomDefinitionsDiscovery,
    discover_project_tools,
)


GREET_TOOL = '''\
def greet(name: str) -> str:
    """Return a friendly greeting."""
    return f"Hello, {name}!"


def _private_helper():
    return 1
'''

DECORATED_TOOL = '''\
from praisonaiagents import tool


@tool
def add(a: int, b: int) -> int:
    """Add two numbers."""
    return a + b


def helper():
    """Plain callable dropped when a @tool exists in the same module."""
    return "helper"
'''


@pytest.fixture
def project(tmp_path, monkeypatch):
    """Create a project with a .praisonai/tools/ dir and cwd into it."""
    tools_dir = tmp_path / ".praisonai" / "tools"
    tools_dir.mkdir(parents=True)
    monkeypatch.chdir(tmp_path)
    # No git root: keep the walk-up bounded to this tmp tree.
    monkeypatch.setattr(
        "praisonai_code.cli.features.custom_definitions.get_git_root",
        lambda: tmp_path,
    )
    return tools_dir


class TestToolDiscovery:
    def test_discovers_plain_callable_namespaced(self, project, monkeypatch):
        monkeypatch.setenv("PRAISONAI_ALLOW_LOCAL_TOOLS", "true")
        (project / "greet.py").write_text(GREET_TOOL)

        discovery = CustomDefinitionsDiscovery()
        tools = discovery.list_tools()

        names = {t.name for t in tools}
        assert "greet.greet" in names
        # Private helpers are excluded.
        assert "greet._private_helper" not in names
        # Namespaced by module filename.
        greet = discovery.get_tool("greet.greet")
        assert greet is not None
        assert greet.source == "project"

    def test_discover_project_tools_returns_callables(self, project, monkeypatch):
        monkeypatch.setenv("PRAISONAI_ALLOW_LOCAL_TOOLS", "true")
        (project / "greet.py").write_text(GREET_TOOL)

        callables = discover_project_tools()
        assert len(callables) == 1
        assert callables[0]("Ada") == "Hello, Ada!"

    def test_gate_blocks_discovery_when_env_unset(self, project, monkeypatch):
        monkeypatch.delenv("PRAISONAI_ALLOW_LOCAL_TOOLS", raising=False)
        (project / "greet.py").write_text(GREET_TOOL)

        assert discover_project_tools() == []

    def test_decorated_tool_preferred_over_plain_helper(self, project, monkeypatch):
        monkeypatch.setenv("PRAISONAI_ALLOW_LOCAL_TOOLS", "true")
        (project / "mixed.py").write_text(DECORATED_TOOL)

        discovery = CustomDefinitionsDiscovery()
        names = {t.name for t in discovery.list_tools()}
        # The @tool-decorated function wins; the plain helper is dropped.
        assert "mixed.add" in names
        assert "mixed.helper" not in names

    def test_underscore_modules_skipped(self, project, monkeypatch):
        monkeypatch.setenv("PRAISONAI_ALLOW_LOCAL_TOOLS", "true")
        (project / "_ignored.py").write_text(GREET_TOOL)
        (project / "greet.py").write_text(GREET_TOOL)

        discovery = CustomDefinitionsDiscovery()
        names = {t.name for t in discovery.list_tools()}
        assert "greet.greet" in names
        assert not any(n.startswith("_ignored") for n in names)

    def test_no_tools_dir_is_noop(self, tmp_path, monkeypatch):
        monkeypatch.setenv("PRAISONAI_ALLOW_LOCAL_TOOLS", "true")
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(
            "praisonai_code.cli.features.custom_definitions.get_git_root",
            lambda: tmp_path,
        )
        assert discover_project_tools() == []


class TestUserGlobalTools:
    def test_user_global_tools_load_outside_cwd(self, tmp_path, monkeypatch):
        """User-global ~/.praisonai/tools/*.py must load even though they live
        outside the project CWD (regression: the safe loader's CWD boundary
        previously silently dropped them)."""
        monkeypatch.setenv("PRAISONAI_ALLOW_LOCAL_TOOLS", "true")

        # Separate the "home" tree from the project CWD so the user tool is
        # genuinely outside the working directory.
        user_root = tmp_path / "home"
        (user_root / ".praisonai" / "tools").mkdir(parents=True)
        (user_root / ".praisonai" / "tools" / "greet.py").write_text(GREET_TOOL)

        project_dir = tmp_path / "project"
        project_dir.mkdir()
        monkeypatch.chdir(project_dir)
        monkeypatch.setattr(
            "praisonai_code.cli.features.custom_definitions.get_git_root",
            lambda: project_dir,
        )
        monkeypatch.setattr(
            CustomDefinitionsDiscovery,
            "_get_user_dir",
            lambda self: user_root / ".praisonai",
        )

        discovery = CustomDefinitionsDiscovery()
        greet = discovery.get_tool("greet.greet")
        assert greet is not None
        assert greet.source == "user"
        assert greet.callable("Ada") == "Hello, Ada!"


class TestCustomAgentToolWiring:
    """`praisonai run --agent ...` must also auto-load project-local tools,
    unioned with the frontmatter ``tools:`` list (regression: `_run_custom_agent`
    previously ignored --tools and never auto-discovered)."""

    def test_run_custom_agent_merges_project_tools(self, project, monkeypatch):
        monkeypatch.setenv("PRAISONAI_ALLOW_LOCAL_TOOLS", "true")
        (project / "greet.py").write_text(GREET_TOOL)

        import praisonaiagents
        from praisonai_code.cli.commands import run as run_mod

        captured = {}

        class _FakeAgent:
            def __init__(self, **config):
                captured["config"] = config

            def start(self, prompt):
                return "done"

        monkeypatch.setattr(praisonaiagents, "Agent", _FakeAgent)
        # Keep the event bridge and session usage recording inert.
        monkeypatch.setattr(run_mod, "_record_session_usage", lambda *a, **k: None)

        agent_config = {"name": "assistant", "tools": ["internet_search"]}
        run_mod._run_custom_agent(agent_config, "hi", no_save=True)

        tools = captured["config"].get("tools", [])
        # Frontmatter tool name string preserved.
        assert "internet_search" in tools
        # Auto-discovered project callable appended.
        assert any(callable(t) and getattr(t, "__name__", "") == "greet" for t in tools)

    def test_run_custom_agent_no_discovery_without_optin(self, project, monkeypatch):
        monkeypatch.delenv("PRAISONAI_ALLOW_LOCAL_TOOLS", raising=False)
        (project / "greet.py").write_text(GREET_TOOL)

        import praisonaiagents
        from praisonai_code.cli.commands import run as run_mod

        captured = {}

        class _FakeAgent:
            def __init__(self, **config):
                captured["config"] = config

            def start(self, prompt):
                return "done"

        monkeypatch.setattr(praisonaiagents, "Agent", _FakeAgent)
        monkeypatch.setattr(run_mod, "_record_session_usage", lambda *a, **k: None)

        agent_config = {"name": "assistant", "tools": ["internet_search"]}
        run_mod._run_custom_agent(agent_config, "hi", no_save=True)

        tools = captured["config"].get("tools", [])
        assert tools == ["internet_search"]

    def test_run_custom_agent_dedupes_internal_duplicates(self, project, monkeypatch):
        """Internal duplicates within the resolved extra tools (e.g. overlapping
        --tools/--toolset) must be de-duplicated by identity, not just against
        the frontmatter list."""
        monkeypatch.delenv("PRAISONAI_ALLOW_LOCAL_TOOLS", raising=False)

        import praisonaiagents
        from praisonai_code.cli.commands import run as run_mod

        captured = {}

        class _FakeAgent:
            def __init__(self, **config):
                captured["config"] = config

            def start(self, prompt):
                return "done"

        def _dup_tool():
            return "dup"

        monkeypatch.setattr(praisonaiagents, "Agent", _FakeAgent)
        monkeypatch.setattr(run_mod, "_record_session_usage", lambda *a, **k: None)
        # Same callable resolved twice (overlapping sources).
        monkeypatch.setattr(
            run_mod, "_resolve_tools_arg", lambda *a, **k: [_dup_tool, _dup_tool]
        )

        agent_config = {"name": "assistant", "tools": []}
        run_mod._run_custom_agent(agent_config, "hi", tools="x", no_save=True)

        tools = captured["config"].get("tools", [])
        assert tools.count(_dup_tool) == 1


class TestAgentsCommandsUnaffected:
    def test_agents_still_discovered_alongside_tools(self, project, monkeypatch):
        monkeypatch.setenv("PRAISONAI_ALLOW_LOCAL_TOOLS", "true")
        agents_dir = project.parent / "agents"
        agents_dir.mkdir()
        (agents_dir / "helper.md").write_text(
            "---\nrole: Helper\n---\nYou are a helper.\n"
        )
        (project / "greet.py").write_text(GREET_TOOL)

        discovery = CustomDefinitionsDiscovery()
        assert discovery.get_agent("helper") is not None
        assert discovery.get_tool("greet.greet") is not None
