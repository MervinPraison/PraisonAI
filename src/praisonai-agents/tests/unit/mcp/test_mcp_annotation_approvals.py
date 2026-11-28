"""TDD unit tests for MCP tool annotation -> approval risk mapping and per-entry approval overrides."""

from __future__ import annotations

import asyncio
import logging
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest


class _RecordingBackend:
    """Minimal ApprovalProtocol backend recording requests and returning a fixed decision."""

    def __init__(self, *, approved: bool = True, reason: str = "recorded"):
        self.requests = []
        self.approved = approved
        self.reason = reason

    def request_approval_sync(self, request):
        from praisonaiagents.approval.protocols import ApprovalDecision

        self.requests.append(request)
        return ApprovalDecision(approved=self.approved, reason=self.reason)

    async def request_approval(self, request):
        from praisonaiagents.approval.protocols import ApprovalDecision

        self.requests.append(request)
        return ApprovalDecision(approved=self.approved, reason=self.reason)


def _make_stub_mcp(raw_tools, *, approval=None):
    """Build a lightweight MCP instance around stubbed stdio tools without spawning a subprocess."""
    from praisonaiagents.mcp.mcp import MCP

    mcp = object.__new__(MCP)
    mcp.is_sse = False
    mcp.is_http_stream = False
    mcp.is_websocket = False
    mcp.is_npx = False
    mcp.debug = False
    mcp.timeout = 30
    mcp.allowed_tools = None
    mcp.disabled_tools = None
    mcp._tool_prefix = None
    mcp._registered_server_names = None
    mcp.approval = approval

    called = []
    runner = SimpleNamespace(
        tools=list(raw_tools),
        resources=[],
        resource_templates=[],
        prompts=[],
        _dead=None,
        call_tool=lambda name, args: (called.append((name, args)) or f"ok:{name}"),
    )
    mcp.runner = runner
    mcp._tools = mcp._apply_tool_filters(mcp._generate_tool_functions())
    return mcp, called


def _make_agent(tools, *, backend=None, name="mcp-approval-agent", permissions=None):
    from praisonaiagents import Agent

    agent = Agent(
        name=name,
        instructions="Test MCP approval annotations.",
        tools=tools,
        llm="gpt-4o-mini",
    )
    if backend is not None:
        agent._approval_backend = backend
    if permissions is not None:
        agent._perm_deny = frozenset(permissions.get("deny", ()))
    return agent


class TestAnnotationRiskMapping:
    """Pure annotation + approval override resolution."""

    def test_readonly_dict_requires_no_approval(self):
        from praisonaiagents.mcp.mcp import resolve_mcp_approval_risk

        assert resolve_mcp_approval_risk({"readOnlyHint": True}) is None
        assert resolve_mcp_approval_risk({"readOnlyHint": True, "destructiveHint": False}) is None

    def test_destructive_dict_returns_high_risk(self):
        from praisonaiagents.mcp.mcp import resolve_mcp_approval_risk

        assert resolve_mcp_approval_risk({"destructiveHint": True}) == "high"
        assert resolve_mcp_approval_risk({"readOnlyHint": True, "destructiveHint": True}) == "high"

    def test_object_annotations_supported(self):
        from praisonaiagents.mcp.mcp import resolve_mcp_approval_risk

        ro = SimpleNamespace(readOnlyHint=True, destructiveHint=False)
        dest = SimpleNamespace(readOnlyHint=False, destructiveHint=True)
        assert resolve_mcp_approval_risk(ro) is None
        assert resolve_mcp_approval_risk(dest) == "high"

    def test_override_always_and_never(self):
        from praisonaiagents.mcp.mcp import resolve_mcp_approval_risk

        assert resolve_mcp_approval_risk({"readOnlyHint": True}, approval="always") == "medium"
        assert resolve_mcp_approval_risk({"destructiveHint": True}, approval="always") == "high"
        assert resolve_mcp_approval_risk({"destructiveHint": True}, approval="never") is None

    def test_invalid_approval_mode_raises(self):
        from praisonaiagents.mcp.mcp import resolve_mcp_approval_risk

        with pytest.raises(ValueError, match="approval"):
            resolve_mcp_approval_risk(None, approval="sometimes")


class TestAgentMCPAnnotationApprovals:
    """End-to-end approval gating through Agent for MCP tools."""

    def test_readonly_tool_runs_without_approval(self):
        raw = [
            SimpleNamespace(
                name="list_issues",
                description="List issues",
                inputSchema={"type": "object", "properties": {}},
                annotations={"readOnlyHint": True},
            )
        ]
        mcp, _ = _make_stub_mcp(raw)
        backend = _RecordingBackend(approved=False)
        agent = _make_agent(mcp, backend=backend)

        decision = agent._resolve_approval_decision("list_issues", {}, is_async=False)
        assert decision.approved is True
        assert backend.requests == []

    def test_destructive_tool_requires_high_risk_approval_and_blocks_on_deny(self):
        raw = [
            SimpleNamespace(
                name="drop_records",
                description="Delete records permanently",
                inputSchema={"type": "object", "properties": {"id": {"type": "string"}}},
                annotations=SimpleNamespace(readOnlyHint=False, destructiveHint=True),
            )
        ]
        mcp, _ = _make_stub_mcp(raw)
        backend = _RecordingBackend(approved=False, reason="user denied destructive op")
        agent = _make_agent(mcp, backend=backend)

        err = agent._check_tool_approval_sync("drop_records", {"id": "42"})
        assert isinstance(err, dict) and err.get("approval_denied") is True
        assert len(backend.requests) == 1
        assert backend.requests[0].tool_name == "drop_records"
        assert backend.requests[0].risk_level == "high"

    def test_destructive_tool_routes_high_risk_via_registry_backend_sync_and_async(self):
        from praisonaiagents.approval import get_approval_registry

        raw = [
            SimpleNamespace(
                name="purge_bucket",
                description="Purge bucket",
                inputSchema={"type": "object", "properties": {}},
                annotations={"destructiveHint": True},
            )
        ]
        mcp, _ = _make_stub_mcp(raw)
        backend = _RecordingBackend(approved=False, reason="denied via registry")
        agent = _make_agent(mcp, name="reg-mcp-agent")
        agent._approval_backend = None

        registry = get_approval_registry()
        prev_backend = registry.get_backend("reg-mcp-agent")
        registry.set_backend(backend, agent_name="reg-mcp-agent")
        try:
            dec_sync = agent._resolve_approval_decision("purge_bucket", {}, is_async=False)
            assert dec_sync.approved is False
            assert len(backend.requests) == 1
            assert backend.requests[0].risk_level == "high"

            dec_async = asyncio.run(
                agent._resolve_approval_decision("purge_bucket", {}, is_async=True)
            )
            assert dec_async.approved is False
            assert len(backend.requests) == 2
            assert backend.requests[1].risk_level == "high"
        finally:
            registry.set_backend(prev_backend, agent_name="reg-mcp-agent")

    def test_approval_always_gates_even_readonly_tools(self):
        raw = [
            SimpleNamespace(
                name="read_status",
                description="Read status",
                inputSchema={"type": "object", "properties": {}},
                annotations={"readOnlyHint": True},
            )
        ]
        mcp, _ = _make_stub_mcp(raw, approval="always")
        backend = _RecordingBackend(approved=False, reason="always ask")
        agent = _make_agent(mcp, backend=backend)

        err = agent._check_tool_approval_sync("read_status", {})
        assert isinstance(err, dict) and err.get("approval_denied") is True
        assert len(backend.requests) == 1
        assert backend.requests[0].tool_name == "read_status"

    def test_approval_never_skips_annotation_approval_but_respects_agent_deny(self):
        raw = [
            SimpleNamespace(
                name="nuke_cache",
                description="Clear cache",
                inputSchema={"type": "object", "properties": {}},
                annotations={"destructiveHint": True},
            )
        ]
        mcp, _ = _make_stub_mcp(raw, approval="never")
        backend = _RecordingBackend(approved=False)
        agent = _make_agent(mcp, backend=backend)

        decision = agent._resolve_approval_decision("nuke_cache", {}, is_async=False)
        assert decision.approved is True
        assert backend.requests == []

        # Explicit agent deny rules must still block even when server has approval="never".
        denied_agent = _make_agent(mcp, backend=backend, permissions={"deny": ["nuke_cache"]})
        res = denied_agent._check_tool_approval_sync("nuke_cache", {})
        assert isinstance(res, dict) and res.get("permission_denied") is True

    def test_prefixed_mcp_tool_preserves_approval_risk(self):
        raw = [
            SimpleNamespace(
                name="delete_repo",
                description="Delete repository",
                inputSchema={"type": "object", "properties": {}},
                annotations={"destructiveHint": True},
            )
        ]
        mcp, _ = _make_stub_mcp(raw)
        mcp.with_tool_prefix("github")
        try:
            backend = _RecordingBackend(approved=False)
            agent = _make_agent(mcp, backend=backend)

            err = agent._check_tool_approval_sync("github_delete_repo", {})
            assert isinstance(err, dict) and err.get("approval_denied") is True
            assert len(backend.requests) == 1
            assert backend.requests[0].risk_level == "high"
        finally:
            mcp._release_registered_names()

    def test_http_stream_mcp_tool_carries_annotations_and_gates_approval(self):
        from praisonaiagents.mcp.mcp_http_stream import HTTPStreamMCPTool

        http_tool = HTTPStreamMCPTool(
            name="delete_project",
            description="Delete project",
            session=MagicMock(),
            input_schema={"type": "object", "properties": {}},
            annotations={"destructiveHint": True},
        )
        backend = _RecordingBackend(approved=False)
        agent = _make_agent([http_tool], backend=backend)

        err = agent._check_tool_approval_sync("delete_project", {})
        assert isinstance(err, dict) and err.get("approval_denied") is True
        assert len(backend.requests) == 1
        assert backend.requests[0].risk_level == "high"


class TestFromConfigApprovalForwarding:
    """MCP.from_config / build_mcp forwarding and validation of per-entry approval."""

    def test_from_config_forwards_approval_without_warning(self, caplog):
        from praisonaiagents.mcp.loader import build_mcp

        captured = {}

        class _RecMCP:
            def __init__(self, target, args=None, **kw):
                captured["target"] = target
                captured["args"] = args
                captured["kw"] = kw

        with caplog.at_level(logging.WARNING, logger="praisonaiagents.mcp.loader"):
            build_mcp(
                {"url": "https://api.example.com/mcp", "approval": "always"},
                name="github",
                cls=_RecMCP,
            )

        assert captured["target"] == "https://api.example.com/mcp"
        assert captured["kw"]["approval"] == "always"
        assert not any("unknown field" in r.message for r in caplog.records)

    def test_from_config_omits_approval_when_not_specified(self):
        from praisonaiagents.mcp.loader import build_mcp

        captured = {}

        class _RecMCP:
            def __init__(self, target, args=None, **kw):
                captured["kw"] = kw

        build_mcp({"url": "https://api.example.com/mcp"}, name="srv", cls=_RecMCP)
        assert "approval" not in captured["kw"]

    def test_from_config_rejects_invalid_approval_value(self):
        from praisonaiagents.mcp.loader import build_mcp

        class _RecMCP:
            def __init__(self, target, args=None, **kw):
                pass

        with pytest.raises(ValueError, match="approval"):
            build_mcp(
                {"url": "https://api.example.com/mcp", "approval": "prompt"},
                name="srv",
                cls=_RecMCP,
            )
