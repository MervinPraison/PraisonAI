"""A deep-copied Agent is a separate approval scope.

Apps copy one configured Agent per user or tenant. A "this session" approval
granted to one copy must not cover another, and closing a copy must not drop
the original's grants. ``clone_for_channel`` already mints a fresh scope id;
``copy.deepcopy`` now does the same.
"""

import copy

import pytest

from praisonaiagents import Agent, tool
from praisonaiagents.approval import ApprovalDecision, get_approval_registry
from praisonaiagents.approval.backends import CallbackBackend


@tool
def shell_exec(command: str) -> str:
    """Run a shell command."""
    return "ran"


@pytest.fixture
def prompts(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("PRAISONAI_HOME", str(tmp_path))
    asked = []
    reg = get_approval_registry()
    # The attribute, not get_backend(): that builds a ConsoleBackend when none is set.
    old_backend = reg._global_backend
    was_required = reg.is_required("shell_exec")
    old_risk = reg.get_risk_level("shell_exec")
    reg.add_requirement("shell_exec", "high")

    def person(name, args, risk):
        asked.append(name)
        return ApprovalDecision(approved=True, approver="human", scope="session")

    reg.set_backend(CallbackBackend(person))
    try:
        yield asked
    finally:
        if old_backend is None:
            reg.remove_backend()
        else:
            reg.set_backend(old_backend)
        if was_required:
            reg.add_requirement("shell_exec", old_risk)
        else:
            reg.remove_requirement("shell_exec")
        reg.clear_approved()


def _run(agent):
    agent.execute_tool("shell_exec", {"command": "id"})


def test_deepcopy_gets_its_own_scope_id():
    original = Agent(name="assistant", instructions="x", output="silent")
    copied = copy.deepcopy(original)
    assert copied._approval_scope_id != original._approval_scope_id
    assert copied._approval_scope_id.startswith("assistant:")


def test_session_grant_does_not_cover_a_deep_copy(prompts):
    original = Agent(name="assistant", instructions="x", tools=[shell_exec], output="silent")
    copied = copy.deepcopy(original)
    _run(original)
    _run(original)
    assert len(prompts) == 1  # the session grant covers the original
    _run(copied)
    assert len(prompts) == 2  # the copy is asked on its own
