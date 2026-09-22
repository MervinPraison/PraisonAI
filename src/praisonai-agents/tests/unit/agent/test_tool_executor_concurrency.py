"""Concurrent timeouts must retire their own executor only once."""

import concurrent.futures
import threading

import pytest

from praisonaiagents import Agent
from praisonaiagents.agent import async_safety
from praisonaiagents.agent.tool_execution import ToolExecutionMixin
from praisonaiagents.config import ExecutionConfig
from praisonaiagents.escalation.loop_guard import LoopGuard, LoopGuardConfig


def test_standalone_mixin_initializes_one_lock_for_concurrent_callers(monkeypatch):
    barrier = threading.Barrier(2)

    class ConcurrentLock(async_safety.DualLock):
        def __init__(self):
            super().__init__()
            barrier.wait(timeout=5)

    instance = ToolExecutionMixin()
    with monkeypatch.context() as context:
        context.setattr(async_safety, "DualLock", ConcurrentLock)
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as callers:
            first = callers.submit(instance._get_tool_executor_lock)
            second = callers.submit(instance._get_tool_executor_lock)
            assert first.result(timeout=5) is second.result(timeout=5)

    assert instance._get_tool_executor_lock() is not ToolExecutionMixin()._get_tool_executor_lock()


@pytest.mark.parametrize("initialize_lock", [False, True])
def test_executor_lock_allows_tool_bodies_to_run_concurrently(monkeypatch, initialize_lock):
    barrier = threading.Barrier(2)

    def paired_tool(value: int) -> str:
        """Wait for the other invocation, except during initialization."""
        if value:
            barrier.wait(timeout=5)
        return str(value)

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    agent = Agent(
        instructions="Test tools",
        tools=[paired_tool],
        output="silent",
        execution=ExecutionConfig(max_retry_limit=0, context_compaction=False),
    )
    agent._loop_guard = LoopGuard(LoopGuardConfig(enabled=False))
    assert agent._execute_tool_with_context("paired_tool", {"value": 0}, None) == "0"
    if not initialize_lock:
        del agent._tool_executor_lock
    agent._tool_timeout = 10
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as callers:
            calls = [
                callers.submit(agent._execute_tool_with_context, "paired_tool", {"value": value}, None)
                for value in (1, 2)
            ]
            assert [call.result(timeout=10) for call in calls] == ["1", "2"]
    finally:
        agent.close()


@pytest.mark.parametrize("create_replacement", [False, True])
def test_late_timeout_does_not_retire_another_calls_executor(monkeypatch, create_replacement):
    executor_class = concurrent.futures.ThreadPoolExecutor
    waiting = threading.Barrier(2)
    first_submitted = threading.Event()
    finish_second = threading.Event()
    release_tools = threading.Event()
    executors = []

    class ControlledExecutor(executor_class):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.calls = 0
            executors.append(self)

        def submit(self, *args, **kwargs):
            future = super().submit(*args, **kwargs)
            self.calls += 1
            call_number = self.calls
            if self is executors[0]:
                if call_number == 1:
                    first_submitted.set()
                # Order two genuine outstanding calls' timeout notifications.
                # No sleep or wall-clock deadline determines the interleaving.
                def timeout_result(timeout=None):
                    waiting.wait(timeout=5)
                    if call_number == 2:
                        assert finish_second.wait(timeout=5)
                    raise concurrent.futures.TimeoutError()

                future.result = timeout_result
            return future

    def blocking_tool(call: int) -> str:
        """Wait until the test releases the outstanding tool calls."""
        assert release_tools.wait(timeout=10)
        return str(call)

    def quick_tool() -> str:
        """Return without blocking."""
        return "ready"

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    agent = Agent(
        name="concurrent-timeouts",
        instructions="Test tools",
        tools=[blocking_tool, quick_tool],
        output="silent",
        execution=ExecutionConfig(max_retry_limit=0, context_compaction=False),
    )
    assert agent._execute_tool_with_context("quick_tool", {}, None) == "ready"
    agent._tool_timeout = 1
    monkeypatch.setattr(concurrent.futures, "ThreadPoolExecutor", ControlledExecutor)
    # Seed the shared pool so this test isolates retirement from lazy creation.
    agent._tool_executor = ControlledExecutor(max_workers=2)

    def execute(call):
        return agent._execute_tool_with_context("blocking_tool", {"call": call}, None)

    try:
        with executor_class(max_workers=2) as callers:
            first = callers.submit(execute, 1)
            # The submit order fixes which future receives the first timeout.
            assert first_submitted.wait(timeout=5)
            second = callers.submit(execute, 2)
            try:
                first_result = first.result(timeout=5)
                assert first_result.get("timeout") is True
                replacement = None
                if create_replacement:
                    assert agent._execute_tool_with_context("quick_tool", {}, None) == "ready"
                    replacement = agent._tool_executor
            finally:
                finish_second.set()
            second_result = second.result(timeout=5)

        assert second_result.get("timeout") is True
        assert agent._tool_executor_orphaned == 1
        assert agent._tool_executor is replacement
        if replacement is not None:
            assert replacement.submit(lambda: "usable").result(timeout=5) == "usable"
    finally:
        finish_second.set()
        release_tools.set()
        for executor in executors:
            executor.shutdown(wait=True)
        agent.close()
