"""Tests for cooperative interrupt aborting an in-flight shell subprocess.

Verifies that a running shell command is terminated promptly when the agent's
cancellation Event fires (issue #4596), instead of running until its timeout.
"""

import os
import sys
import threading
import time

import pytest

from praisonaiagents.tools.shell_tools import ShellTools
from praisonaiagents.tools.injected import AgentState, with_injection_context
from praisonaiagents.agent.interrupt import InterruptController


@pytest.fixture(autouse=True)
def _auto_approve(monkeypatch):
    # execute_command is approval-gated (critical); auto-approve for the test.
    monkeypatch.setenv("PRAISONAI_AUTO_APPROVE", "true")


def _state_with(cancel_event):
    return AgentState(
        agent_id="test",
        run_id="run",
        session_id="sess",
        cancel_event=cancel_event,
    )


def test_interrupt_aborts_running_command_within_grace():
    """A long sleep is interrupted well before its timeout and reports interrupted."""
    controller = InterruptController()
    tools = ShellTools()

    result_holder = {}

    def run():
        state = _state_with(controller.event)
        with with_injection_context(state):
            result_holder["result"] = tools.execute_command(
                f"{sys.executable} -c \"import time; time.sleep(30)\"",
                timeout=30,
            )

    worker = threading.Thread(target=run)
    start = time.time()
    worker.start()
    time.sleep(0.5)  # let the subprocess start
    controller.request("user_stop")
    worker.join(timeout=10)
    elapsed = time.time() - start

    assert not worker.is_alive(), "shell command was not aborted"
    assert elapsed < 10, f"interrupt took too long: {elapsed:.1f}s"
    result = result_holder["result"]
    assert result.get("interrupted") is True
    assert result.get("success") is False


def test_no_cancel_event_preserves_normal_behaviour():
    """Without a cancel_event a quick command still returns normally."""
    tools = ShellTools()
    result = tools.execute_command(f"{sys.executable} -c \"print('hi')\"", timeout=10)
    assert result.get("success") is True
    assert "hi" in result.get("stdout", "")
