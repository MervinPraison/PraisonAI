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
