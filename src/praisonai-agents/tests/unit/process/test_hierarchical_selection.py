"""Regression tests for hierarchical manager task selection (issue #3700).

The hierarchical manager must never select the synthetic ``manager_task`` for
execution. Runtime task IDs are 0-based; the injected ``manager_task`` lands
last. Previously validation only checked ``selected_task_id in self.tasks``,
which is ``True`` for ``manager_task`` and let the manager delegate to itself
so the real user task never ran.
"""

import asyncio

import pytest

from praisonaiagents.agent.agent import Agent
from praisonaiagents.task.task import Task
from praisonaiagents.process.process import Process
from praisonaiagents.process.manager_schema import ManagerInstructions


def _build_process():
    worker = Agent(name="Worker", role="Analyst", goal="Analyze", backstory="Analyst")
    user_task = Task(
        name="user_task",
        description="Say BANANA",
        expected_output="BANANA",
        agent=worker,
    )
    tasks = {}
    process = Process(tasks=tasks, agents=[worker], manager_llm="gpt-4o-mini")

    def add_task(task):
        tid = len(tasks)
        task.id = tid
        tasks[tid] = task
        return tid

    add_task(user_task)
    return process, user_task, add_task


def _drive_sync(process, add_task, instruction_sequence):
    """Drive the sync hierarchical generator with mocked manager instructions."""
    calls = {"n": 0}

    def fake_instructions(manager_task, manager_prompt, schema):
        i = min(calls["n"], len(instruction_sequence) - 1)
        calls["n"] += 1
        return instruction_sequence[i]

    process._get_manager_instructions_with_fallback = fake_instructions

    gen = process.hierarchical()
    manager_task = next(gen)  # first yield is the synthetic manager_task
    manager_id = add_task(manager_task)

    yielded = []
    try:
        sent = manager_id
        while True:
            value = gen.send(sent)
            yielded.append(value)
            # Mark the yielded (delegated) task complete so the loop progresses.
            process.tasks[value].status = "completed"
            sent = None
    except StopIteration:
        pass
    return yielded, calls["n"]


def test_reject_manager_task_id_selection_sync():
    process, user_task, add_task = _build_process()
    # manager_task will get id 1; user task is id 0.
    seq = [
        ManagerInstructions(task_id=1, agent_name="manager_task", action="execute"),
        ManagerInstructions(task_id=0, agent_name="Worker", action="execute"),
    ]
    yielded, _ = _drive_sync(process, add_task, seq)

    # Only the real user task (id 0) should ever be yielded for execution.
    assert yielded == [0]
    assert 1 not in yielded


def test_valid_user_task_id_still_executes_sync():
    process, user_task, add_task = _build_process()
    seq = [ManagerInstructions(task_id=0, agent_name="Worker", action="execute")]
    yielded, _ = _drive_sync(process, add_task, seq)
    assert yielded == [0]


def test_exhausted_self_selection_does_not_run_manager_task_sync(caplog):
    import logging

    process, user_task, add_task = _build_process()
    # Manager always self-selects; must never yield the manager_task for execution.
    seq = [ManagerInstructions(task_id=1, agent_name="manager_task", action="execute")]
    with caplog.at_level(logging.WARNING):
        yielded, _ = _drive_sync(process, add_task, seq)
    assert yielded == []
    # The re-prompt warning must advertise only the delegable user id (0),
    # never the synthetic manager_task id (1).
    assert "valid IDs: [0]" in caplog.text


def _drive_async(process, add_task, instruction_sequence):
    calls = {"n": 0}

    # The async loop offloads the sync fallback via asyncio.to_thread by default
    # (manager_task.async_execution is False), so mock the sync method.
    def fake_instructions(manager_task, manager_prompt, schema):
        i = min(calls["n"], len(instruction_sequence) - 1)
        calls["n"] += 1
        return instruction_sequence[i]

    process._get_manager_instructions_with_fallback = fake_instructions

    async def run():
        gen = process.ahierarchical()
        manager_task = await gen.asend(None)
        manager_id = add_task(manager_task)
        yielded = []
        sent = manager_id
        try:
            while True:
                value = await gen.asend(sent)
                yielded.append(value)
                process.tasks[value].status = "completed"
                sent = None
        except StopAsyncIteration:
            pass
        return yielded

    return asyncio.run(run())


def test_reject_manager_task_id_selection_async():
    process, user_task, add_task = _build_process()
    seq = [
        ManagerInstructions(task_id=1, agent_name="manager_task", action="execute"),
        ManagerInstructions(task_id=0, agent_name="Worker", action="execute"),
    ]
    yielded = _drive_async(process, add_task, seq)
    assert yielded == [0]
    assert 1 not in yielded


def test_precompleted_task_lets_loop_terminate_sync():
    """Re-running a team whose task is already ``completed`` must still be able
    to terminate normally: pre-completed tasks are seeded into the completion
    count so ``completed_count`` can reach ``total_tasks`` without relying on the
    manager emitting ``stop``. Regression for the hierarchical termination gap.
    """
    process, user_task, add_task = _build_process()
    # Simulate a prior run: the single user task (id 0) is already completed.
    process.tasks[0].status = "completed"
    # Manager keeps re-selecting the already-completed task; without seeding the
    # count this would loop until MAX_INVALID_SELECTIONS / stop. With the fix the
    # loop never enters because completed_count already equals total_tasks.
    seq = [ManagerInstructions(task_id=0, agent_name="Worker", action="execute")]
    yielded, _ = _drive_sync(process, add_task, seq)
    # Nothing new to execute; the loop exits immediately.
    assert yielded == []


def test_precompleted_task_lets_loop_terminate_async():
    process, user_task, add_task = _build_process()
    process.tasks[0].status = "completed"
    seq = [ManagerInstructions(task_id=0, agent_name="Worker", action="execute")]
    yielded = _drive_async(process, add_task, seq)
    assert yielded == []


def test_reselected_completed_task_not_double_counted_sync():
    """A manager that re-selects a task after it completes must not advance the
    counter twice and skip a genuinely unexecuted task."""
    worker = Agent(name="Worker", role="Analyst", goal="Analyze", backstory="Analyst")
    t0 = Task(name="t0", description="A", expected_output="A", agent=worker)
    t1 = Task(name="t1", description="B", expected_output="B", agent=worker)
    tasks = {}
    process = Process(tasks=tasks, agents=[worker], manager_llm="gpt-4o-mini")

    def add_task(task):
        tid = len(tasks)
        task.id = tid
        tasks[tid] = task
        return tid

    add_task(t0)  # id 0
    add_task(t1)  # id 1
    # Execute t0, then manager re-selects the now-completed t0 (ignored, not
    # counted again), then finally executes t1. Both real tasks must run.
    seq = [
        ManagerInstructions(task_id=0, agent_name="Worker", action="execute"),
        ManagerInstructions(task_id=0, agent_name="Worker", action="execute"),
        ManagerInstructions(task_id=1, agent_name="Worker", action="execute"),
    ]
    yielded, _ = _drive_sync(process, add_task, seq)
    assert yielded == [0, 1]


def test_stale_manager_from_prior_run_lets_loop_terminate_sync():
    """Re-running the same team injects a fresh synthetic ``manager_task`` while
    the prior run's manager stays in ``self.tasks``. The stale manager must be
    excluded from ``total_tasks`` so ``completed_count`` can reach it and the
    loop terminates normally after the single real user task completes — instead
    of looping forever because a phantom "task" can never be executed.
    """
    process, user_task, add_task = _build_process()  # user task id 0

    # Simulate a completed prior run: its synthetic manager was injected (id 1)
    # and recorded, and the user task is already completed.
    prior_manager = Task(name="manager_task", description="prior", expected_output="x")
    prior_id = add_task(prior_manager)  # id 1
    process._synthetic_manager_task_ids.add(prior_id)
    process.tasks[prior_id].status = "completed"
    process.tasks[0].status = "completed"

    # Second run: manager keeps selecting the already-completed user task. Without
    # excluding the stale manager, total_tasks would be 2 (user + stale manager)
    # but only the user task can ever complete -> infinite manager loop. With the
    # fix total_tasks is 1 and the seeded count makes the loop exit immediately.
    seq = [ManagerInstructions(task_id=0, agent_name="Worker", action="execute")]
    yielded, _ = _drive_sync(process, add_task, seq)
    assert yielded == []


def test_aborted_prior_manager_not_selectable_sync(caplog):
    """A stale manager left NOT completed by an aborted prior run must still be
    rejected as a delegation target (by id) and excluded from the count so the
    loop can finish once the real work is done."""
    import logging

    process, user_task, add_task = _build_process()  # user task id 0

    prior_manager = Task(name="manager_task", description="prior", expected_output="x")
    prior_id = add_task(prior_manager)  # id 1 — aborted: left "not started"
    process._synthetic_manager_task_ids.add(prior_id)

    # Manager tries to delegate to the stale manager (id 1), then to the real
    # user task (id 0). The stale id must be refused and absent from valid IDs.
    seq = [
        ManagerInstructions(task_id=1, agent_name="Worker", action="execute"),
        ManagerInstructions(task_id=0, agent_name="Worker", action="execute"),
    ]
    with caplog.at_level(logging.WARNING):
        yielded, _ = _drive_sync(process, add_task, seq)
    # Only the real user task runs; the stale manager (id 1) is never executed.
    assert yielded == [0]
    assert 1 not in yielded
    # Re-prompt must advertise only the delegable user id, never the stale manager.
    assert "valid IDs: [0]" in caplog.text


def test_stale_manager_from_prior_run_lets_loop_terminate_async():
    process, user_task, add_task = _build_process()  # user task id 0
    prior_manager = Task(name="manager_task", description="prior", expected_output="x")
    prior_id = add_task(prior_manager)  # id 1
    process._synthetic_manager_task_ids.add(prior_id)
    process.tasks[prior_id].status = "completed"
    process.tasks[0].status = "completed"
    seq = [ManagerInstructions(task_id=0, agent_name="Worker", action="execute")]
    yielded = _drive_async(process, add_task, seq)
    assert yielded == []


def test_user_task_named_manager_task_is_still_delegable_sync():
    """Rejection must key off the synthetic task's *id*, not its name, so a
    legitimate user task named ``manager_task`` (id 0) still executes while the
    synthetic manager (id 1) is refused."""
    worker = Agent(name="Worker", role="Analyst", goal="Analyze", backstory="Analyst")
    user_task = Task(
        name="manager_task",  # user deliberately reuses the reserved-looking name
        description="Say BANANA",
        expected_output="BANANA",
        agent=worker,
    )
    tasks = {}
    process = Process(tasks=tasks, agents=[worker], manager_llm="gpt-4o-mini")

    def add_task(task):
        tid = len(tasks)
        task.id = tid
        tasks[tid] = task
        return tid

    add_task(user_task)  # id 0
    seq = [ManagerInstructions(task_id=0, agent_name="Worker", action="execute")]
    yielded, _ = _drive_sync(process, add_task, seq)
    # The user task at id 0 must run even though it shares the synthetic name.
    assert yielded == [0]
