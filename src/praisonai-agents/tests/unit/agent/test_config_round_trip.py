"""An Agent can be exported to config and rebuilt.

Config flowed one way: workflows/yaml_parser.py builds agents FROM YAML and
nothing exported them back, so a team assembled in Python could not be handed to
the visual builder or diffed against another.
"""
import json
import pytest

from praisonaiagents import Agent
from praisonaiagents.agent.serialize import (
    AGENT_CONFIG_VERSION,
    SerializationError,
    agent_from_dict,
    agent_to_dict,
    team_to_dict,
)


def search(q: str) -> str:
    """Search the web."""
    return "result"


class TestRoundTrip:
    def test_identity_survives(self):
        agent = Agent(name="Researcher", role="Analyst", instructions="be thorough", llm="gpt-4o")
        rebuilt = agent_from_dict(agent_to_dict(agent))
        assert (rebuilt.name, rebuilt.role, rebuilt.llm) == ("Researcher", "Analyst", "gpt-4o")

    def test_the_config_is_json_safe(self):
        """It has to survive a file or an HTTP body to be worth anything."""
        agent = Agent(name="R", instructions="x", llm="gpt-4o", tools=[search])
        json.dumps(agent_to_dict(agent))

    def test_tools_are_exported_by_name_and_can_be_rebound(self):
        agent = Agent(name="R", instructions="x", llm="gpt-4o", tools=[search])
        blob = agent_to_dict(agent)
        assert blob["tools"] == ["search"]
        assert blob["tools_resolvable"] is True
        rebuilt = agent_from_dict(blob, tool_registry={"search": search})
        assert [t.__name__ for t in rebuilt.tools] == ["search"]


class TestItRefusesToLoseThings:
    def test_tools_without_a_registry_are_refused(self):
        """Rebuilding tool-less would look like an agent that chose not to act."""
        blob = agent_to_dict(Agent(name="R", instructions="x", llm="gpt-4o", tools=[search]))
        with pytest.raises(SerializationError, match="tool_registry"):
            agent_from_dict(blob)

    def test_a_registry_missing_a_tool_is_refused_by_name(self):
        blob = agent_to_dict(Agent(name="R", instructions="x", llm="gpt-4o", tools=[search]))
        with pytest.raises(SerializationError, match="search"):
            agent_from_dict(blob, tool_registry={"other": search})

    def test_control_a_tool_less_agent_needs_no_registry(self):
        blob = agent_to_dict(Agent(name="R", instructions="x", llm="gpt-4o"))
        assert agent_from_dict(blob).name == "R"

    def test_a_config_from_another_version_is_refused(self):
        blob = agent_to_dict(Agent(name="R", instructions="x", llm="gpt-4o"))
        blob["version"] = AGENT_CONFIG_VERSION + 1
        with pytest.raises(SerializationError, match="version"):
            agent_from_dict(blob)

    def test_exporting_none_is_refused(self):
        with pytest.raises(SerializationError):
            agent_to_dict(None)


class TestOnlyConstructorArguments:
    def test_the_export_contains_nothing_the_constructor_rejects(self):
        """The first draft exported attributes that had moved into output=,
        producing a config that could not be imported."""
        agent = Agent(name="R", instructions="x", llm="gpt-4o")
        blob = agent_to_dict(agent)
        agent_from_dict(blob)  # must not raise

    def test_runtime_state_is_not_exported(self):
        blob = agent_to_dict(Agent(name="R", instructions="x", llm="gpt-4o"))
        for leaked in ("chat_history", "_session", "memory", "knowledge"):
            assert leaked not in blob


class TestTeams:
    def test_a_team_exports_its_members(self):
        class FakeTeam:
            name = "ops"
            process = "sequential"
            agents = [Agent(name="A", instructions="x", llm="gpt-4o"),
                      Agent(name="B", instructions="x", llm="gpt-4o")]

        blob = team_to_dict(FakeTeam())
        assert blob["name"] == "ops"
        assert [a["name"] for a in blob["agents"]] == ["A", "B"]
