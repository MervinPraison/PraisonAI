"""Tests for @require_approval bound-method arg binding and per-agent active scope.

Verifies that when an Agent approves a bound-method tool decorated with
``@require_approval`` (such as ``execute_command`` or ``write_file``):
1. ``_bind_call_args`` drops the bound-method receiver (``self`` / ``cls``) only
   when it is the first parameter of the callable's signature.
2. ``Agent.execute_tool`` and ``Agent.execute_tool_async`` activate the agent's
   approval scope for the duration of the approved invocation so the inner
   ``@require_approval`` wrapper matches the agent's scoped approval cache
   without double-prompting or failing closed in non-interactive mode.
3. Cross-agent isolation, bare-call protection outside ``active_scope``, and
   ``BEFORE_TOOL`` hook denials all remain intact.
"""

import io
import pytest

from praisonaiagents import Agent
from praisonaiagents.approval import (
    ApprovalConfig,
    ApprovalDecision,
    _bind_call_args,
    clear_approval_context,
    get_approval_registry,
)
from praisonaiagents.hooks import HookDecision, HookEvent, HookRegistry, HookResult
from praisonaiagents.tools import execute_command, write_file


class _DenyBackend:
    """Test backend that always denies and counts calls."""

    def __init__(self):
        self.calls = 0

    def request_approval_sync(self, request):
        self.calls += 1
        return ApprovalDecision(approved=False, reason="denied by test backend")

    async def request_approval(self, request):
        self.calls += 1
        return ApprovalDecision(approved=False, reason="denied by test backend")


@pytest.fixture(autouse=True)
def _clean_approval_state():
    reg = get_approval_registry()
    old_global = reg._global_backend
    clear_approval_context()
    yield
    reg._global_backend = old_global
    clear_approval_context()


def test_bind_call_args_drops_receiver_only_when_first_param():
    class Sample:
        def method(self, command: str, timeout: int = 30):
            return command

        @classmethod
        def cls_method(cls, path: str):
            return path

    def plain_with_self_second(command: str, self: str = "keep"):
        return (command, self)

    inst = Sample()
    assert _bind_call_args(Sample.method, (inst,), {"command": "echo hi"}) == {
        "command": "echo hi"
    }
    assert _bind_call_args(Sample.__dict__["cls_method"].__func__, (Sample, "/tmp/x"), {}) == {
        "path": "/tmp/x"
    }
    assert _bind_call_args(plain_with_self_second, ("echo hi", "val"), {}) == {
        "command": "echo hi",
        "self": "val",
    }


def test_sync_execute_tool_bound_methods_succeed_non_interactively(monkeypatch, tmp_path):
    # Ensure any fallback to console stdin fails closed rather than hanging.
    monkeypatch.setattr("sys.stdin", io.StringIO(""))
    monkeypatch.chdir(tmp_path)
    reg = get_approval_registry()
    deny = _DenyBackend()
    reg.set_backend(deny)

    agent = Agent(
        name="approved_sync_agent",
        instructions="Test agent",
        tools=[execute_command, write_file],
        approval=True,
    )

    cmd_result = agent.execute_tool("execute_command", {"command": "echo BOUND_OK"})
    assert isinstance(cmd_result, dict), cmd_result
    assert cmd_result.get("success") is True, cmd_result
    assert "BOUND_OK" in cmd_result.get("stdout", ""), cmd_result
    assert deny.calls == 0

    target = tmp_path / "out.txt"
    write_result = agent.execute_tool(
        "write_file",
        {"filepath": str(target), "content": "hello-bound"},
    )
    assert write_result is True, write_result
    assert target.read_text(encoding="utf-8") == "hello-bound"
    assert deny.calls == 0


@pytest.mark.asyncio
async def test_async_execute_tool_bound_methods_succeed_non_interactively(monkeypatch, tmp_path):
    monkeypatch.setattr("sys.stdin", io.StringIO(""))
    monkeypatch.chdir(tmp_path)
    reg = get_approval_registry()
    deny = _DenyBackend()
    reg.set_backend(deny)

    agent = Agent(
        name="approved_async_agent",
        instructions="Test agent",
        tools=[execute_command, write_file],
        approval=True,
    )

    cmd_result = await agent.execute_tool_async(
        "execute_command", {"command": "echo BOUND_OK"}
    )
    assert isinstance(cmd_result, dict), cmd_result
    assert cmd_result.get("success") is True, cmd_result
    assert "BOUND_OK" in cmd_result.get("stdout", ""), cmd_result
    assert deny.calls == 0

    target = tmp_path / "async_out.txt"
    write_result = await agent.execute_tool_async(
        "write_file",
        {"filepath": str(target), "content": "hello-async-bound"},
    )
    assert write_result is True, write_result
    assert target.read_text(encoding="utf-8") == "hello-async-bound"
    assert deny.calls == 0


def test_cross_agent_isolation_and_bare_call_still_require_approval(monkeypatch):
    monkeypatch.setattr("sys.stdin", io.StringIO(""))
    reg = get_approval_registry()
    deny = _DenyBackend()
    reg.set_backend(deny)

    agent_a = Agent(
        name="agent_a",
        instructions="Approved agent",
        tools=[execute_command],
        approval=True,
    )
    agent_b = Agent(
        name="agent_b",
        instructions="Deny-backend agent",
        tools=[execute_command],
        approval=ApprovalConfig(backend=deny, permissions={"allow": ["execute_command"]}),
    )
    agent_default = Agent(
        name="agent_default",
        instructions="Default-policy agent",
        tools=[execute_command],
    )

    res_a = agent_a.execute_tool("execute_command", {"command": "echo BOUND_OK"})
    assert isinstance(res_a, dict) and res_a.get("success") is True

    # Agent B (same tool & identical args) must NOT inherit Agent A's approval.
    res_b = agent_b.execute_tool("execute_command", {"command": "echo BOUND_OK"})
    assert isinstance(res_b, dict) and res_b.get("approval_denied") is True, res_b
    assert deny.calls == 1

    # Default agent is also blocked.
    res_default = agent_default.execute_tool("execute_command", {"command": "echo BOUND_OK"})
    assert isinstance(res_default, dict) and (
        res_default.get("approval_denied") is True or res_default.get("permission_denied") is True
    ), res_default

    # Outside active_scope, a bare call must still require approval.
    assert reg._active_scope.get(None) is None
    with pytest.raises(PermissionError):
        execute_command("echo BOUND_OK")


def test_active_scope_resets_on_exception():
    reg = get_approval_registry()
    assert reg._active_scope.get(None) is None
    with pytest.raises(RuntimeError):
        with reg.active_scope("scope-x"):
            assert reg._active_scope.get(None) == "scope-x"
            raise RuntimeError("boom")
    assert reg._active_scope.get(None) is None


def test_before_tool_hook_deny_still_blocks_with_approval_true(monkeypatch):
    monkeypatch.setattr("sys.stdin", io.StringIO(""))

    def _block_shell(hook_input):
        return HookResult(decision=HookDecision.DENY, reason="blocked by hook")

    hook_registry = HookRegistry()
    hook_registry.register_function(HookEvent.BEFORE_TOOL, _block_shell)
    agent = Agent(
        name="hooked_agent",
        instructions="Test agent",
        tools=[execute_command],
        approval=True,
        hooks={"registry": hook_registry},
    )

    result = agent.execute_tool("execute_command", {"command": "echo SHOULD_NOT_RUN"})
    assert "SHOULD_NOT_RUN" not in str(result), result
    assert "blocked" in str(result).lower(), result


@pytest.mark.asyncio
async def test_before_tool_hook_deny_still_blocks_async_with_approval_true(monkeypatch):
    monkeypatch.setattr("sys.stdin", io.StringIO(""))

    def _block_shell(hook_input):
        return HookResult(decision=HookDecision.DENY, reason="blocked by hook")

    hook_registry = HookRegistry()
    hook_registry.register_function(HookEvent.BEFORE_TOOL, _block_shell)
    agent = Agent(
        name="hooked_async_agent",
        instructions="Test agent",
        tools=[execute_command],
        approval=True,
        hooks={"registry": hook_registry},
    )

    result = await agent.execute_tool_async("execute_command", {"command": "echo SHOULD_NOT_RUN"})
    assert "SHOULD_NOT_RUN" not in str(result), result
    assert "blocked" in str(result).lower(), result
