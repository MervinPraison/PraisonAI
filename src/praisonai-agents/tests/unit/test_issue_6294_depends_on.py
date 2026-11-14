"""Regression tests for issue #6294: depends_on ordering for sequential teams."""
import pytest


def _team(tasks, process="sequential"):
    from praisonaiagents import AgentTeam
    return AgentTeam(agents=[tasks[0].agent], tasks=tasks, process=process)


def _make_tasks():
    from praisonaiagents import Agent, Task
    a = Agent(name="a", instructions="x", llm="gpt-4o-mini")
    t1 = Task(name="t1", description="d1", agent=a, expected_output="o")
    t2 = Task(name="t2", description="d2", agent=a, expected_output="o", depends_on=[t1])
    return t1, t2


def test_sequential_depends_on_orders_tasks():
    t1, t2 = _make_tasks()
    team = _team([t2, t1])
    assert [t.name for t in team.tasks.values()] == ["t1", "t2"]


def test_sequential_cycle_keeps_list_order(caplog):
    t1, t2 = _make_tasks()
    t1.depends_on = [t2]
    with caplog.at_level("WARNING"):
        team = _team([t1, t2])
    assert [t.name for t in team.tasks.values()] == ["t1", "t2"]
    assert "Circular" in caplog.text


def test_sequential_dependency_outside_team_is_ignored():
    t1, t2 = _make_tasks()
    team = _team([t2])
    assert [t.name for t in team.tasks.values()] == ["t2"]


def test_reuse_auto_wired_task_in_second_team():
    # Sequential auto-wiring sets c.context=[b]; reusing c alone must still work.
    from praisonaiagents import Agent, Task
    ag = Agent(name="a", instructions="x", llm="gpt-4o-mini")
    a, b, c = (Task(name=n, description="d", agent=ag, expected_output="o") for n in "abc")
    _team([a, b, c])
    assert b in (c.context or [])
    team = _team([c])
    assert [t.name for t in team.tasks.values()] == ["c"]


def test_linear_order_unchanged():
    from praisonaiagents import Agent, Task
    a = Agent(name="a", instructions="x", llm="gpt-4o-mini")
    tasks = [Task(name=f"t{i}", description="d", agent=a, expected_output="o") for i in range(3)]
    team = _team(tasks)
    assert [t.name for t in team.tasks.values()] == ["t0", "t1", "t2"]


def test_deep_reverse_chain_does_not_recurse():
    import sys
    from praisonaiagents import Agent, Task
    from praisonaiagents.agents.agents import AgentTeam
    a = Agent(name="a", instructions="x", llm="gpt-4o-mini")
    n = sys.getrecursionlimit() + 100
    tasks = [Task(name="t0", description="d", agent=a, expected_output="o")]
    for i in range(1, n):
        tasks.append(Task(name=f"t{i}", description="d", agent=a,
                          expected_output="o", depends_on=[tasks[-1]]))
    ordered = AgentTeam._order_tasks_by_dependencies(list(reversed(tasks)))
    assert ordered == tasks


def test_workflow_keeps_order_and_allows_context_loops():
    # Workflow picks its start task by position and may use context cycles as
    # feedback loops, so it must not be reordered or rejected.
    t1, t2 = _make_tasks()
    t1.depends_on = [t2]
    team = _team([t2, t1], "workflow")
    assert [t.name for t in team.tasks.values()] == ["t2", "t1"]
