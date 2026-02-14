"""
TDD tests for AgentApproval backend.

Tests the agent-based approval backend that delegates approval decisions
to another AI agent in the core SDK.
"""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, AsyncMock

import pytest


# ── Protocol Conformance ────────────────────────────────────────────────────


class TestAgentApprovalProtocol:
    def test_conforms_to_approval_protocol(self):
        from praisonaiagents.approval.protocols import ApprovalProtocol
        from praisonaiagents.approval.backends import AgentApproval

        mock_agent = MagicMock()
        backend = AgentApproval(approver_agent=mock_agent)
        assert isinstance(backend, ApprovalProtocol)

    def test_has_request_approval_sync(self):
        from praisonaiagents.approval.backends import AgentApproval

        backend = AgentApproval(approver_agent=MagicMock())
        assert hasattr(backend, "request_approval_sync")
        assert callable(backend.request_approval_sync)

    def test_has_request_approval_async(self):
        from praisonaiagents.approval.backends import AgentApproval

        backend = AgentApproval(approver_agent=MagicMock())
        assert asyncio.iscoroutinefunction(backend.request_approval)


# ── Construction ────────────────────────────────────────────────────────────


class TestAgentApprovalInit:
    def test_with_explicit_agent(self):
        from praisonaiagents.approval.backends import AgentApproval

        mock_agent = MagicMock()
        mock_agent.name = "my-reviewer"
        backend = AgentApproval(approver_agent=mock_agent)
        assert backend._approver_agent is mock_agent

    def test_repr_with_agent(self):
        from praisonaiagents.approval.backends import AgentApproval

        mock_agent = MagicMock()
        mock_agent.name = "sec-bot"
        backend = AgentApproval(approver_agent=mock_agent)
        assert "sec-bot" in repr(backend)

    def test_repr_without_agent(self):
        from praisonaiagents.approval.backends import AgentApproval

        backend = AgentApproval()
        assert "default" in repr(backend)


# ── Prompt Builder ──────────────────────────────────────────────────────────


class TestPromptBuilder:
    def _make_request(self, **overrides):
        from praisonaiagents.approval.protocols import ApprovalRequest

        defaults = {
            "tool_name": "execute_command",
            "arguments": {"cmd": "rm -rf /"},
            "risk_level": "critical",
            "agent_name": "worker",
        }
        defaults.update(overrides)
        return ApprovalRequest(**defaults)

    def test_prompt_contains_tool_name(self):
        from praisonaiagents.approval.backends import AgentApproval

        backend = AgentApproval(approver_agent=MagicMock())
        prompt = backend._build_prompt(self._make_request(tool_name="delete_file"))
        assert "delete_file" in prompt

    def test_prompt_contains_risk_level(self):
        from praisonaiagents.approval.backends import AgentApproval

        backend = AgentApproval(approver_agent=MagicMock())
        prompt = backend._build_prompt(self._make_request(risk_level="high"))
        assert "HIGH" in prompt

    def test_prompt_contains_arguments(self):
        from praisonaiagents.approval.backends import AgentApproval

        backend = AgentApproval(approver_agent=MagicMock())
        prompt = backend._build_prompt(self._make_request(arguments={"path": "/tmp"}))
        assert "/tmp" in prompt

    def test_prompt_ends_with_instruction(self):
        from praisonaiagents.approval.backends import AgentApproval

        backend = AgentApproval(approver_agent=MagicMock())
        prompt = backend._build_prompt(self._make_request())
        assert "APPROVE" in prompt
        assert "DENY" in prompt


# ── Async Approval Flow ────────────────────────────────────────────────────


class TestApprovalFlowAsync:
    def _make_request(self, **overrides):
        from praisonaiagents.approval.protocols import ApprovalRequest

        defaults = {
            "tool_name": "execute_command",
            "arguments": {"cmd": "ls"},
            "risk_level": "low",
            "agent_name": "worker",
        }
        defaults.update(overrides)
        return ApprovalRequest(**defaults)

    def test_approved_by_agent(self):
        from praisonaiagents.approval.backends import AgentApproval

        mock_agent = MagicMock()
        mock_agent.name = "reviewer"
        mock_agent.achat = AsyncMock(return_value="APPROVE")

        backend = AgentApproval(approver_agent=mock_agent)
        decision = asyncio.run(backend.request_approval(self._make_request()))
        assert decision.approved is True
        assert decision.approver == "reviewer"

    def test_denied_by_agent(self):
        from praisonaiagents.approval.backends import AgentApproval

        mock_agent = MagicMock()
        mock_agent.name = "reviewer"
        mock_agent.achat = AsyncMock(return_value="DENY")

        backend = AgentApproval(approver_agent=mock_agent)
        decision = asyncio.run(backend.request_approval(self._make_request()))
        assert decision.approved is False

    def test_ambiguous_response_denied(self):
        """If response contains both APPROVE and DENY, it's denied."""
        from praisonaiagents.approval.backends import AgentApproval

        mock_agent = MagicMock()
        mock_agent.name = "reviewer"
        mock_agent.achat = AsyncMock(return_value="I would APPROVE but actually DENY this")

        backend = AgentApproval(approver_agent=mock_agent)
        decision = asyncio.run(backend.request_approval(self._make_request()))
        assert decision.approved is False

    def test_falls_back_to_sync_chat(self):
        """If agent has no achat, uses chat via executor."""
        from praisonaiagents.approval.backends import AgentApproval

        mock_agent = MagicMock()
        mock_agent.name = "reviewer"
        # Remove achat so it falls back to chat
        del mock_agent.achat
        mock_agent.chat = MagicMock(return_value="APPROVE")

        backend = AgentApproval(approver_agent=mock_agent)
        decision = asyncio.run(backend.request_approval(self._make_request()))
        assert decision.approved is True

    def test_error_returns_denial(self):
        from praisonaiagents.approval.backends import AgentApproval

        mock_agent = MagicMock()
        mock_agent.name = "reviewer"
        mock_agent.achat = AsyncMock(side_effect=RuntimeError("LLM down"))

        backend = AgentApproval(approver_agent=mock_agent)
        decision = asyncio.run(backend.request_approval(self._make_request()))
        assert decision.approved is False
        assert "error" in decision.reason.lower()

    def test_metadata_contains_response(self):
        from praisonaiagents.approval.backends import AgentApproval

        mock_agent = MagicMock()
        mock_agent.name = "reviewer"
        mock_agent.achat = AsyncMock(return_value="APPROVE - this looks safe")

        backend = AgentApproval(approver_agent=mock_agent)
        decision = asyncio.run(backend.request_approval(self._make_request()))
        assert decision.metadata.get("platform") == "agent"
        assert "safe" in decision.metadata.get("response", "")


# ── Export / Import ─────────────────────────────────────────────────────────


class TestExports:
    def test_import_from_approval_package(self):
        from praisonaiagents.approval import AgentApproval
        assert AgentApproval is not None

    def test_import_from_backends(self):
        from praisonaiagents.approval.backends import AgentApproval
        assert AgentApproval is not None
