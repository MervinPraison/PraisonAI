import pytest


def _make_agent():
    from praisonaiagents import Agent

    return Agent(name="Writer", instructions="Write")


def _make_task(agent):
    from praisonaiagents import Task

    return Task(description="Write a bio", expected_output="A bio", agent=agent)


def test_tasks_str_raises_type_error():
    from praisonaiagents import AgentTeam

    agent = _make_agent()
    with pytest.raises(TypeError, match="Task"):
        AgentTeam(agents=[agent], tasks="Write one sentence")


def test_tasks_bytes_raises_type_error():
    from praisonaiagents import AgentTeam

    agent = _make_agent()
    with pytest.raises(TypeError):
        AgentTeam(agents=[agent], tasks=b"Write one sentence")


def test_tasks_non_sequence_raises_type_error():
    from praisonaiagents import AgentTeam

    agent = _make_agent()
    with pytest.raises(TypeError):
        AgentTeam(agents=[agent], tasks=123)


def test_tasks_non_task_element_reports_index():
    from praisonaiagents import AgentTeam

    agent = _make_agent()
    task = _make_task(agent)
    with pytest.raises(TypeError, match=r"tasks\[1\]"):
        AgentTeam(agents=[agent], tasks=[task, "not a task"])


def test_tasks_empty_list_raises_value_error():
    from praisonaiagents import AgentTeam

    agent = _make_agent()
    with pytest.raises(ValueError):
        AgentTeam(agents=[agent], tasks=[])


def test_tasks_tuple_of_task_accepted():
    from praisonaiagents import AgentTeam

    agent = _make_agent()
    task = _make_task(agent)
    team = AgentTeam(agents=[agent], tasks=(task,))
    assert len(team.tasks) == 1


def test_tasks_none_auto_generates():
    from praisonaiagents import AgentTeam

    agent = _make_agent()
    team = AgentTeam(agents=[agent], tasks=None)
    assert len(team.tasks) == 1
