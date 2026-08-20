"""AgentTeam(llm=) / AgentFlow(llm=) must actually reach the agents.

Regression tests for the bug where AgentTeam stored `self.llm = llm` and nothing
read it, so members silently kept gpt-4o-mini, and where AgentFlow(llm=) reached
only the agents it built itself, never a ready-made Agent step.
"""
import pytest

from praisonaiagents import Agent, AgentTeam
from praisonaiagents.workflows import AgentFlow

TEAM_MODEL = "anthropic/claude-sonnet-4-5"


def test_team_llm_fills_in_members_without_a_model():
    member = Agent(name="m", instructions="x")
    team = AgentTeam(agents=[member], llm=TEAM_MODEL)
    assert team.llm == TEAM_MODEL
    assert member.llm == TEAM_MODEL
    # and it is a real LLM selection, not just a relabelled attribute
    assert member.llm_instance is not None
    assert member.llm_instance.model == TEAM_MODEL


def test_team_llm_does_not_override_an_explicit_member_model():
    pinned = Agent(name="p", instructions="x", llm="gpt-4o")
    AgentTeam(agents=[pinned], llm=TEAM_MODEL)
    assert pinned.llm == "gpt-4o"


def test_team_llm_does_not_override_model_kwarg():
    pinned = Agent(name="p", instructions="x", model="gpt-4o")
    AgentTeam(agents=[pinned], llm=TEAM_MODEL)
    assert pinned.llm == "gpt-4o"


def test_team_without_llm_changes_nothing():
    member = Agent(name="m", instructions="x")
    before = member.llm
    AgentTeam(agents=[member])
    assert member.llm == before


def test_manager_llm_is_a_separate_concept():
    member = Agent(name="m", instructions="x")
    team = AgentTeam(agents=[member], llm=TEAM_MODEL, manager_llm="gpt-4o")
    assert team.manager_llm == "gpt-4o"      # manager keeps its own model
    assert member.llm == TEAM_MODEL          # members get the team default


def test_flow_llm_reaches_a_ready_made_agent_step():
    member = Agent(name="m", instructions="x")
    pinned = Agent(name="p", instructions="x", llm="gpt-4o")
    flow = AgentFlow(steps=[member, pinned], llm=TEAM_MODEL)
    # _run_impl applies the default before executing; do just that step.
    for agent in flow._collect_agents():
        agent._apply_default_llm(flow.llm)
    assert member.llm == TEAM_MODEL
    assert pinned.llm == "gpt-4o"


def test_team_and_flow_agree():
    a, b = Agent(name="a", instructions="x"), Agent(name="b", instructions="x")
    AgentTeam(agents=[a], llm=TEAM_MODEL)
    flow = AgentFlow(steps=[b], llm=TEAM_MODEL)
    for agent in flow._collect_agents():
        agent._apply_default_llm(flow.llm)
    assert a.llm == b.llm == TEAM_MODEL


def test_applying_default_invalidates_cached_dispatcher():
    # A used agent caches a dispatcher bound to the previous model. Applying a
    # container default must drop it so the next chat rebuilds with the new one.
    member = Agent(name="m", instructions="x")
    member._unified_dispatcher = object()  # simulate a prior execution
    member._apply_default_llm(TEAM_MODEL)
    assert member.llm == TEAM_MODEL
    assert getattr(member, "_unified_dispatcher", None) is None


def test_pinned_agent_keeps_its_dispatcher():
    # An explicit model is never overridden, so its dispatcher must be left alone.
    pinned = Agent(name="p", instructions="x", llm="gpt-4o")
    sentinel = object()
    pinned._unified_dispatcher = sentinel
    pinned._apply_default_llm(TEAM_MODEL)
    assert pinned.llm == "gpt-4o"
    assert pinned._unified_dispatcher is sentinel
