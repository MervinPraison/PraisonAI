"""Tests for exposing named agents as delegatable subagents.

Covers the wrapper seam that turns discovered ``.praisonai/agents/*.md``
definitions into delegation targets for the running agent.
"""

from praisonai_code.cli.features.custom_definitions import (
    CustomAgent,
    build_subagent_resolver,
    list_delegatable_agents,
    _agent_config_from_definition,
)


def _make_agent(name, mode=None, goal=None, tools=None, model=None):
    from pathlib import Path

    return CustomAgent(
        name=name,
        path=Path(f"<test:{name}>"),
        model=model,
        tools=tools,
        goal=goal,
        instructions=f"You are {name}.",
        mode=mode,
        source="project",
    )


class TestAgentConfigFromDefinition:
    def test_subagent_mode_is_not_treated_as_permission_mode(self):
        """`mode: subagent` must not raise as an unknown permission mode."""
        agent = _make_agent("researcher", mode="subagent", goal="Research")
        config = _agent_config_from_definition(agent)
        assert config["name"] == "researcher"
        assert config["goal"] == "Research"
        assert "permissions" not in config

    def test_frontmatter_fields_carried_through(self):
        agent = _make_agent(
            "coder", model="gpt-4o", tools=["read_file"], goal="Write code"
        )
        config = _agent_config_from_definition(agent)
        assert config["llm"] == "gpt-4o"
        assert config["tools"] == ["read_file"]
        assert config["goal"] == "Write code"

    def test_read_only_mode_still_resolves_permissions(self):
        agent = _make_agent("planner", mode="read-only")
        config = _agent_config_from_definition(agent)
        assert config["permissions"]["edit:*"] == "deny"


class TestListDelegatableAgents:
    def test_allow_list_takes_precedence(self, monkeypatch):
        agents = [
            _make_agent("researcher", mode="subagent"),
            _make_agent("reviewer"),
            _make_agent("coder"),
        ]
        monkeypatch.setattr(
            "praisonai_code.cli.features.custom_definitions."
            "CustomDefinitionsDiscovery.list_agents",
            lambda self: agents,
        )
        result = list_delegatable_agents(["reviewer", "coder"])
        names = {a.name for a in result}
        assert names == {"reviewer", "coder"}

    def test_mode_subagent_marker_used_without_allow_list(self, monkeypatch):
        agents = [
            _make_agent("researcher", mode="subagent"),
            _make_agent("reviewer"),
        ]
        monkeypatch.setattr(
            "praisonai_code.cli.features.custom_definitions."
            "CustomDefinitionsDiscovery.list_agents",
            lambda self: agents,
        )
        result = list_delegatable_agents(None)
        assert [a.name for a in result] == ["researcher"]


class TestBuildSubagentResolver:
    def test_returns_none_when_no_delegatable_agents(self, monkeypatch):
        monkeypatch.setattr(
            "praisonai_code.cli.features.custom_definitions."
            "CustomDefinitionsDiscovery.list_agents",
            lambda self: [_make_agent("reviewer")],
        )
        resolver, descriptions = build_subagent_resolver(None)
        assert resolver is None
        assert descriptions == {}

    def test_descriptions_fall_back_to_goal(self, monkeypatch):
        monkeypatch.setattr(
            "praisonai_code.cli.features.custom_definitions."
            "CustomDefinitionsDiscovery.list_agents",
            lambda self: [_make_agent("researcher", mode="subagent", goal="Find facts")],
        )
        resolver, descriptions = build_subagent_resolver(None)
        assert resolver is not None
        assert descriptions["researcher"] == "Find facts"

    def test_resolver_returns_none_for_unknown_name(self, monkeypatch):
        monkeypatch.setattr(
            "praisonai_code.cli.features.custom_definitions."
            "CustomDefinitionsDiscovery.list_agents",
            lambda self: [_make_agent("researcher", mode="subagent")],
        )
        resolver, _ = build_subagent_resolver(None)
        assert resolver("does-not-exist") is None
