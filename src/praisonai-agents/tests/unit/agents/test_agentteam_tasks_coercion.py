"""AgentTeam.tasks must not accept bare strings (char iteration bug)."""

import pytest

from praisonaiagents import Agent, AgentTeam, Task


def test_agentteam_rejects_string_tasks():
    writer = Agent(name="W", role="W", goal="g", instructions="i")
    reviewer = Agent(name="R", role="R", goal="g", instructions="i")
    with pytest.raises(TypeError, match="not str"):
        AgentTeam(agents=[writer, reviewer], tasks="Write one sentence.")


def test_agentteam_accepts_task_list():
    writer = Agent(name="W", role="W", goal="g", instructions="i")
    task = Task(description="Do work", agent=writer)
    team = AgentTeam(agents=[writer], tasks=[task])
    assert len(team.tasks) == 1


def test_agentteam_auto_tasks_none():
    writer = Agent(name="W", role="W", goal="g", instructions="i")
    team = AgentTeam(agents=[writer], tasks=None)
    assert len(team.tasks) >= 1
