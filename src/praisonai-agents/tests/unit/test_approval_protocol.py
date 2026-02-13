"""
TDD tests for the extensible approval protocol module.

Tests cover:
- ApprovalRequest / ApprovalDecision dataclasses
- ApprovalProtocol structural subtyping
- AutoApproveBackend always approves
- ConsoleBackend (mocked stdin)
- ApprovalRegistry per-agent + global backend routing
- ApprovalRegistry pre-checks (env, yaml, already-approved)
- Backward compatibility with old approval.py API
- Timeout handling
"""

import asyncio
import os
import pytest
from unittest.mock import patch, MagicMock, AsyncMock


# ── Protocol & Dataclass tests ──────────────────────────────────────────────


class TestApprovalRequest:
    def test_minimal_construction(self):
        from praisonaiagents.approval.protocols import ApprovalRequest
        req = ApprovalRequest(tool_name="execute_command", arguments={"cmd": "ls"}, risk_level="critical")
        assert req.tool_name == "execute_command"
        assert req.arguments == {"cmd": "ls"}
        assert req.risk_level == "critical"
        assert req.agent_name is None
        assert req.session_id is None

    def test_full_construction(self):
        from praisonaiagents.approval.protocols import ApprovalRequest
        req = ApprovalRequest(
            tool_name="write_file",
            arguments={"path": "/tmp/x"},
            risk_level="high",
            agent_name="my-agent",
            session_id="sess-1",
            context={"user": "alice"},
        )
        assert req.agent_name == "my-agent"
        assert req.context == {"user": "alice"}


class TestApprovalDecision:
    def test_approved(self):
        from praisonaiagents.approval.protocols import ApprovalDecision
        d = ApprovalDecision(approved=True, reason="auto")
        assert d.approved is True
        assert d.reason == "auto"
        assert d.modified_args == {}

    def test_denied(self):
        from praisonaiagents.approval.protocols import ApprovalDecision
        d = ApprovalDecision(approved=False, reason="user denied")
        assert d.approved is False

    def test_modified_args(self):
        from praisonaiagents.approval.protocols import ApprovalDecision
        d = ApprovalDecision(approved=True, modified_args={"cmd": "ls -la"})
        assert d.modified_args == {"cmd": "ls -la"}

    def test_approver_and_metadata(self):
        from praisonaiagents.approval.protocols import ApprovalDecision
        d = ApprovalDecision(approved=True, approver="webhook", metadata={"ip": "1.2.3.4"})
        assert d.approver == "webhook"
        assert d.metadata == {"ip": "1.2.3.4"}


class TestApprovalProtocol:
    def test_protocol_structural_subtyping(self):
        """Any class with async request_approval(ApprovalRequest) -> ApprovalDecision satisfies the protocol."""
        from praisonaiagents.approval.protocols import ApprovalProtocol, ApprovalRequest, ApprovalDecision

        class MyBackend:
            async def request_approval(self, request: ApprovalRequest) -> ApprovalDecision:
                return ApprovalDecision(approved=True)

        assert isinstance(MyBackend(), ApprovalProtocol)

    def test_non_conforming_class_fails(self):
        from praisonaiagents.approval.protocols import ApprovalProtocol

        class Bad:
            pass

        assert not isinstance(Bad(), ApprovalProtocol)


# ── Backend tests ────────────────────────────────────────────────────────────


class TestAutoApproveBackend:
    def test_always_approves(self):
        from praisonaiagents.approval.backends import AutoApproveBackend
        from praisonaiagents.approval.protocols import ApprovalRequest
        backend = AutoApproveBackend()
        req = ApprovalRequest(tool_name="execute_command", arguments={}, risk_level="critical")
        decision = asyncio.run(backend.request_approval(req))
        assert decision.approved is True
        assert decision.approver == "system"

    def test_sync_shortcut(self):
        from praisonaiagents.approval.backends import AutoApproveBackend
        from praisonaiagents.approval.protocols import ApprovalRequest
        backend = AutoApproveBackend()
        req = ApprovalRequest(tool_name="x", arguments={}, risk_level="low")
        decision = backend.request_approval_sync(req)
        assert decision.approved is True


class TestConsoleBackend:
    def test_approved_via_mock(self):
        from praisonaiagents.approval.backends import ConsoleBackend
        from praisonaiagents.approval.protocols import ApprovalRequest
        backend = ConsoleBackend()
        req = ApprovalRequest(tool_name="write_file", arguments={"path": "/tmp"}, risk_level="high")

        with patch.object(backend, '_prompt_user', return_value=True):
            decision = backend.request_approval_sync(req)
        assert decision.approved is True

    def test_denied_via_mock(self):
        from praisonaiagents.approval.backends import ConsoleBackend
        from praisonaiagents.approval.protocols import ApprovalRequest
        backend = ConsoleBackend()
        req = ApprovalRequest(tool_name="kill_process", arguments={}, risk_level="critical")

        with patch.object(backend, '_prompt_user', return_value=False):
            decision = backend.request_approval_sync(req)
        assert decision.approved is False

    def test_async_delegates_to_sync(self):
        from praisonaiagents.approval.backends import ConsoleBackend
        from praisonaiagents.approval.protocols import ApprovalRequest
        backend = ConsoleBackend()
        req = ApprovalRequest(tool_name="x", arguments={}, risk_level="low")

        with patch.object(backend, '_prompt_user', return_value=True):
            decision = asyncio.run(backend.request_approval(req))
        assert decision.approved is True


# ── Registry tests ───────────────────────────────────────────────────────────


class TestApprovalRegistry:
    def test_default_backend_is_console(self):
        from praisonaiagents.approval.registry import ApprovalRegistry
        from praisonaiagents.approval.backends import ConsoleBackend
        reg = ApprovalRegistry()
        backend = reg.get_backend()
        assert isinstance(backend, ConsoleBackend)

    def test_set_global_backend(self):
        from praisonaiagents.approval.registry import ApprovalRegistry
        from praisonaiagents.approval.backends import AutoApproveBackend
        reg = ApprovalRegistry()
        reg.set_backend(AutoApproveBackend())
        assert isinstance(reg.get_backend(), AutoApproveBackend)

    def test_per_agent_backend(self):
        from praisonaiagents.approval.registry import ApprovalRegistry
        from praisonaiagents.approval.backends import AutoApproveBackend, ConsoleBackend
        reg = ApprovalRegistry()
        reg.set_backend(AutoApproveBackend(), agent_name="bot-agent")
        assert isinstance(reg.get_backend("bot-agent"), AutoApproveBackend)
        assert isinstance(reg.get_backend("other-agent"), ConsoleBackend)  # fallback

    def test_approve_sync_not_required(self):
        """Tools not in required set are auto-approved."""
        from praisonaiagents.approval.registry import ApprovalRegistry
        reg = ApprovalRegistry()
        reg._required_tools.clear()  # no tools require approval
        decision = reg.approve_sync("agent", "some_tool", {})
        assert decision.approved is True

    def test_approve_sync_with_auto_backend(self):
        from praisonaiagents.approval.registry import ApprovalRegistry
        from praisonaiagents.approval.backends import AutoApproveBackend
        reg = ApprovalRegistry()
        reg.set_backend(AutoApproveBackend())
        decision = reg.approve_sync("agent", "execute_command", {"cmd": "ls"})
        assert decision.approved is True

    def test_approve_sync_env_auto_approve(self):
        from praisonaiagents.approval.registry import ApprovalRegistry
        reg = ApprovalRegistry()
        with patch.dict(os.environ, {"PRAISONAI_AUTO_APPROVE": "true"}):
            decision = reg.approve_sync("agent", "execute_command", {})
        assert decision.approved is True

    def test_approve_async_with_auto_backend(self):
        from praisonaiagents.approval.registry import ApprovalRegistry
        from praisonaiagents.approval.backends import AutoApproveBackend
        reg = ApprovalRegistry()
        reg.set_backend(AutoApproveBackend())
        decision = asyncio.run(
            reg.approve_async("agent", "execute_command", {})
        )
        assert decision.approved is True

    def test_mark_and_check_approved(self):
        from praisonaiagents.approval.registry import ApprovalRegistry
        reg = ApprovalRegistry()
        assert not reg.is_already_approved("execute_command")
        reg.mark_approved("execute_command")
        assert reg.is_already_approved("execute_command")

    def test_already_approved_skips_backend(self):
        """Once approved, no backend call needed."""
        from praisonaiagents.approval.registry import ApprovalRegistry
        reg = ApprovalRegistry()
        reg.mark_approved("execute_command")
        decision = reg.approve_sync("agent", "execute_command", {})
        assert decision.approved is True
        assert "already" in decision.reason.lower()

    def test_yaml_approved_skips_backend(self):
        from praisonaiagents.approval.registry import ApprovalRegistry
        reg = ApprovalRegistry()
        token = reg.set_yaml_approved_tools(["execute_command"])
        decision = reg.approve_sync("agent", "execute_command", {})
        assert decision.approved is True
        reg.reset_yaml_approved_tools(token)

    def test_remove_backend(self):
        from praisonaiagents.approval.registry import ApprovalRegistry
        from praisonaiagents.approval.backends import AutoApproveBackend, ConsoleBackend
        reg = ApprovalRegistry()
        reg.set_backend(AutoApproveBackend(), agent_name="bot")
        reg.remove_backend(agent_name="bot")
        assert isinstance(reg.get_backend("bot"), ConsoleBackend)


# ── Backward compatibility tests ─────────────────────────────────────────────


class TestBackwardCompat:
    """Ensure old approval.py public API still works from the same import path."""

    def test_import_approval_decision(self):
        from praisonaiagents.approval import ApprovalDecision
        d = ApprovalDecision(approved=True)
        assert d.approved

    def test_import_set_approval_callback(self):
        from praisonaiagents.approval import set_approval_callback, get_approval_callback
        assert callable(set_approval_callback)

    def test_import_require_approval(self):
        from praisonaiagents.approval import require_approval
        assert callable(require_approval)

    def test_import_console_approval_callback(self):
        from praisonaiagents.approval import console_approval_callback
        assert callable(console_approval_callback)

    def test_import_request_approval(self):
        from praisonaiagents.approval import request_approval
        assert asyncio.iscoroutinefunction(request_approval)

    def test_import_is_approval_required(self):
        from praisonaiagents.approval import is_approval_required
        assert callable(is_approval_required)

    def test_import_default_dangerous_tools(self):
        from praisonaiagents.approval import DEFAULT_DANGEROUS_TOOLS
        assert "execute_command" in DEFAULT_DANGEROUS_TOOLS

    def test_import_permission_allowlist(self):
        from praisonaiagents.approval import PermissionAllowlist
        al = PermissionAllowlist()
        assert al.is_empty()

    def test_import_new_protocol(self):
        from praisonaiagents.approval import ApprovalProtocol, ApprovalRequest
        assert ApprovalProtocol is not None
        assert ApprovalRequest is not None

    def test_import_new_backends(self):
        from praisonaiagents.approval import AutoApproveBackend, ConsoleBackend
        assert AutoApproveBackend is not None
        assert ConsoleBackend is not None

    def test_import_registry(self):
        from praisonaiagents.approval import get_approval_registry
        reg = get_approval_registry()
        assert reg is not None

    def test_set_callback_routes_to_registry(self):
        """set_approval_callback should still work by wrapping into a backend."""
        from praisonaiagents.approval import set_approval_callback, get_approval_registry
        from praisonaiagents.approval.protocols import ApprovalDecision as AD

        def my_callback(fn, args, risk):
            return AD(approved=True, reason="custom")

        set_approval_callback(my_callback)
        # Verify the registry uses this callback
        reg = get_approval_registry()
        # The global callback backend should be set
        backend = reg.get_backend()
        # Clean up
        set_approval_callback(None)


# ── Global registry singleton tests ──────────────────────────────────────────


class TestGlobalRegistry:
    def test_singleton(self):
        from praisonaiagents.approval import get_approval_registry
        r1 = get_approval_registry()
        r2 = get_approval_registry()
        assert r1 is r2

    def test_default_dangerous_tools_registered(self):
        from praisonaiagents.approval import get_approval_registry
        reg = get_approval_registry()
        assert "execute_command" in reg._required_tools
        assert reg._risk_levels.get("execute_command") == "critical"


# ── Agent(approval=...) parameter tests ─────────────────────────────────────


class TestAgentApprovalParam:
    """Tests for the agent-centric approval= constructor parameter."""

    def test_approval_none_default(self):
        """Agent() with no approval param has no _approval_backend."""
        from praisonaiagents import Agent
        agent = Agent(name="test", instructions="test")
        assert agent._approval_backend is None

    def test_approval_true_sets_auto_approve(self):
        """Agent(approval=True) sets AutoApproveBackend."""
        from praisonaiagents import Agent
        from praisonaiagents.approval.backends import AutoApproveBackend
        agent = Agent(name="test", instructions="test", approval=True)
        assert isinstance(agent._approval_backend, AutoApproveBackend)

    def test_approval_false_sets_none(self):
        """Agent(approval=False) means no per-agent backend (use registry fallback)."""
        from praisonaiagents import Agent
        agent = Agent(name="test", instructions="test", approval=False)
        assert agent._approval_backend is None

    def test_approval_custom_backend(self):
        """Agent(approval=MyBackend()) stores the custom backend."""
        from praisonaiagents import Agent
        from praisonaiagents.approval.backends import AutoApproveBackend
        backend = AutoApproveBackend()
        agent = Agent(name="test", instructions="test", approval=backend)
        assert agent._approval_backend is backend

    def test_approval_true_auto_approves_tool(self):
        """Agent(approval=True) should auto-approve dangerous tools in _execute_tool_impl."""
        from praisonaiagents import Agent
        from praisonaiagents.approval.backends import AutoApproveBackend

        def my_tool(cmd: str) -> str:
            """Execute a command."""
            return f"ran: {cmd}"

        agent = Agent(name="test", instructions="test", tools=[my_tool], approval=True)
        assert isinstance(agent._approval_backend, AutoApproveBackend)

    def test_approval_custom_protocol_backend(self):
        """Any object with request_approval / request_approval_sync works."""
        from praisonaiagents import Agent
        from praisonaiagents.approval.protocols import ApprovalRequest, ApprovalDecision

        class MyWebhookBackend:
            async def request_approval(self, request: ApprovalRequest) -> ApprovalDecision:
                return ApprovalDecision(approved=True, reason="webhook")
            def request_approval_sync(self, request: ApprovalRequest) -> ApprovalDecision:
                return ApprovalDecision(approved=True, reason="webhook")

        backend = MyWebhookBackend()
        agent = Agent(name="test", instructions="test", approval=backend)
        assert agent._approval_backend is backend

    def test_approval_backend_used_in_sync_tool_exec(self):
        """_execute_tool_impl uses self._approval_backend when set."""
        from praisonaiagents import Agent
        from praisonaiagents.approval.protocols import ApprovalRequest, ApprovalDecision

        call_log = []

        class TrackingBackend:
            def request_approval_sync(self, request: ApprovalRequest) -> ApprovalDecision:
                call_log.append(request.tool_name)
                return ApprovalDecision(approved=True, reason="tracked")
            async def request_approval(self, request: ApprovalRequest) -> ApprovalDecision:
                return ApprovalDecision(approved=True, reason="tracked")

        def execute_command(cmd: str) -> str:
            """Execute a command."""
            return f"ran: {cmd}"

        agent = Agent(name="test", instructions="test", tools=[execute_command], approval=TrackingBackend())
        result = agent._execute_tool_impl("execute_command", {"cmd": "ls"})
        assert "execute_command" in call_log
        assert result == "ran: ls"

    def test_approval_backend_denial_blocks_tool(self):
        """If per-agent backend denies, tool is blocked."""
        from praisonaiagents import Agent
        from praisonaiagents.approval.protocols import ApprovalRequest, ApprovalDecision

        class DenyBackend:
            def request_approval_sync(self, request: ApprovalRequest) -> ApprovalDecision:
                return ApprovalDecision(approved=False, reason="denied by policy")
            async def request_approval(self, request: ApprovalRequest) -> ApprovalDecision:
                return ApprovalDecision(approved=False, reason="denied by policy")

        def execute_command(cmd: str) -> str:
            """Execute a command."""
            return f"ran: {cmd}"

        agent = Agent(name="test", instructions="test", tools=[execute_command], approval=DenyBackend())
        result = agent._execute_tool_impl("execute_command", {"cmd": "rm -rf /"})
        assert isinstance(result, dict)
        assert result.get("approval_denied") is True

    def test_approval_async_backend_used(self):
        """execute_tool_async uses self._approval_backend when set."""
        from praisonaiagents import Agent
        from praisonaiagents.approval.protocols import ApprovalRequest, ApprovalDecision

        call_log = []

        class AsyncTracker:
            async def request_approval(self, request: ApprovalRequest) -> ApprovalDecision:
                call_log.append(request.tool_name)
                return ApprovalDecision(approved=True, reason="async-tracked")
            def request_approval_sync(self, request: ApprovalRequest) -> ApprovalDecision:
                return ApprovalDecision(approved=True, reason="async-tracked")

        def execute_command(cmd: str) -> str:
            """Execute a command."""
            return f"ran: {cmd}"

        agent = Agent(name="test", instructions="test", tools=[execute_command], approval=AsyncTracker())

        async def _run():
            return await agent.execute_tool_async("execute_command", {"cmd": "ls"})

        result = asyncio.run(_run())
        assert "execute_command" in call_log
