"""
Integration tests for the approval system.

Tests multi-backend scenarios, cross-backend compatibility, and
ensures all backends satisfy the ApprovalProtocol contract uniformly.
"""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, AsyncMock

import pytest


# ── All Backends Satisfy Protocol ───────────────────────────────────────────


class TestAllBackendsProtocol:
    """Every approval backend must satisfy ApprovalProtocol."""

    def test_slack_approval_protocol(self):
        from praisonaiagents.approval.protocols import ApprovalProtocol
        from praisonai.bots import SlackApproval

        assert isinstance(SlackApproval(token="xoxb-fake", channel="C1"), ApprovalProtocol)

    def test_telegram_approval_protocol(self):
        from praisonaiagents.approval.protocols import ApprovalProtocol
        from praisonai.bots import TelegramApproval

        assert isinstance(TelegramApproval(token="fake", chat_id="1"), ApprovalProtocol)

    def test_discord_approval_protocol(self):
        from praisonaiagents.approval.protocols import ApprovalProtocol
        from praisonai.bots import DiscordApproval

        assert isinstance(DiscordApproval(token="fake", channel_id="1"), ApprovalProtocol)

    def test_webhook_approval_protocol(self):
        from praisonaiagents.approval.protocols import ApprovalProtocol
        from praisonai.bots import WebhookApproval

        assert isinstance(WebhookApproval(webhook_url="https://example.com"), ApprovalProtocol)

    def test_http_approval_protocol(self):
        from praisonaiagents.approval.protocols import ApprovalProtocol
        from praisonai.bots import HTTPApproval

        assert isinstance(HTTPApproval(port=0), ApprovalProtocol)

    def test_agent_approval_protocol(self):
        from praisonaiagents.approval.protocols import ApprovalProtocol
        from praisonaiagents.approval import AgentApproval

        assert isinstance(AgentApproval(approver_agent=MagicMock()), ApprovalProtocol)

    def test_auto_approve_protocol(self):
        from praisonaiagents.approval.protocols import ApprovalProtocol
        from praisonaiagents.approval import AutoApproveBackend

        assert isinstance(AutoApproveBackend(), ApprovalProtocol)

    def test_console_backend_protocol(self):
        from praisonaiagents.approval.protocols import ApprovalProtocol
        from praisonaiagents.approval import ConsoleBackend

        assert isinstance(ConsoleBackend(), ApprovalProtocol)


# ── All Backends Have Both Sync and Async ───────────────────────────────────


class TestSyncAsyncParity:
    """Every backend must have both request_approval and request_approval_sync."""

    @pytest.mark.parametrize("cls_path,kwargs", [
        ("praisonai.bots._slack_approval.SlackApproval", {"token": "xoxb-f", "channel": "C1"}),
        ("praisonai.bots._telegram_approval.TelegramApproval", {"token": "f", "chat_id": "1"}),
        ("praisonai.bots._discord_approval.DiscordApproval", {"token": "f", "channel_id": "1"}),
        ("praisonai.bots._webhook_approval.WebhookApproval", {"webhook_url": "https://x.com"}),
        ("praisonai.bots._http_approval.HTTPApproval", {"port": 0}),
    ])
    def test_has_both_methods(self, cls_path, kwargs):
        import importlib

        module_path, cls_name = cls_path.rsplit(".", 1)
        mod = importlib.import_module(module_path)
        cls = getattr(mod, cls_name)
        backend = cls(**kwargs)

        assert hasattr(backend, "request_approval")
        assert asyncio.iscoroutinefunction(backend.request_approval)
        assert hasattr(backend, "request_approval_sync")
        assert callable(backend.request_approval_sync)


# ── Agent Can Accept Any Backend ────────────────────────────────────────────


class TestAgentAcceptsAnyBackend:
    """Agent(approval=...) works with every backend."""

    def test_agent_with_slack(self):
        from praisonaiagents import Agent
        from praisonai.bots import SlackApproval

        backend = SlackApproval(token="xoxb-test", channel="C1")
        agent = Agent(name="t", instructions="t", approval=backend)
        assert agent._approval_backend is backend

    def test_agent_with_telegram(self):
        from praisonaiagents import Agent
        from praisonai.bots import TelegramApproval

        backend = TelegramApproval(token="t", chat_id="1")
        agent = Agent(name="t", instructions="t", approval=backend)
        assert agent._approval_backend is backend

    def test_agent_with_discord(self):
        from praisonaiagents import Agent
        from praisonai.bots import DiscordApproval

        backend = DiscordApproval(token="t", channel_id="1")
        agent = Agent(name="t", instructions="t", approval=backend)
        assert agent._approval_backend is backend

    def test_agent_with_webhook(self):
        from praisonaiagents import Agent
        from praisonai.bots import WebhookApproval

        backend = WebhookApproval(webhook_url="https://example.com")
        agent = Agent(name="t", instructions="t", approval=backend)
        assert agent._approval_backend is backend

    def test_agent_with_http(self):
        from praisonaiagents import Agent
        from praisonai.bots import HTTPApproval

        backend = HTTPApproval(port=0)
        agent = Agent(name="t", instructions="t", approval=backend)
        assert agent._approval_backend is backend

    def test_agent_with_agent_approval(self):
        from praisonaiagents import Agent
        from praisonaiagents.approval import AgentApproval

        backend = AgentApproval(approver_agent=MagicMock())
        agent = Agent(name="t", instructions="t", approval=backend)
        assert agent._approval_backend is backend


# ── Multi-Agent Different Backends ──────────────────────────────────────────


class TestMultiAgentDifferentBackends:
    """Different agents in the same process can use different backends."""

    def test_three_agents_three_backends(self):
        from praisonaiagents import Agent
        from praisonai.bots import SlackApproval, TelegramApproval, DiscordApproval

        slack_backend = SlackApproval(token="xoxb-t", channel="C1")
        telegram_backend = TelegramApproval(token="t", chat_id="1")
        discord_backend = DiscordApproval(token="t", channel_id="1")

        agent1 = Agent(name="a1", instructions="t", approval=slack_backend)
        agent2 = Agent(name="a2", instructions="t", approval=telegram_backend)
        agent3 = Agent(name="a3", instructions="t", approval=discord_backend)

        assert agent1._approval_backend is slack_backend
        assert agent2._approval_backend is telegram_backend
        assert agent3._approval_backend is discord_backend
        # No cross-contamination
        assert agent1._approval_backend is not agent2._approval_backend


# ── Shared Base Utilities ───────────────────────────────────────────────────


class TestSharedBaseUtilities:
    """Test the shared _approval_base module."""

    def test_classify_approve_keywords(self):
        from praisonai.bots._approval_base import classify_keyword

        for word in ["yes", "y", "approve", "APPROVE", "Ok", "GO", "confirm"]:
            assert classify_keyword(word) == "approve", f"Failed for {word}"

    def test_classify_deny_keywords(self):
        from praisonai.bots._approval_base import classify_keyword

        for word in ["no", "n", "deny", "DENY", "reject", "Block", "STOP"]:
            assert classify_keyword(word) == "deny", f"Failed for {word}"

    def test_classify_unknown_returns_none(self):
        from praisonai.bots._approval_base import classify_keyword

        assert classify_keyword("maybe") is None
        assert classify_keyword("hello") is None
        assert classify_keyword("") is None

    def test_sync_wrapper_works(self):
        from praisonai.bots._approval_base import sync_wrapper

        async def async_add():
            return 42

        result = sync_wrapper(async_add(), timeout=5)
        assert result == 42


# ── Lazy Loading Verification ───────────────────────────────────────────────


class TestLazyLoading:
    """All backends are lazily loaded via __getattr__."""

    def test_bots_init_lazy_slack(self):
        from praisonai.bots import SlackApproval
        assert SlackApproval.__name__ == "SlackApproval"

    def test_bots_init_lazy_telegram(self):
        from praisonai.bots import TelegramApproval
        assert TelegramApproval.__name__ == "TelegramApproval"

    def test_bots_init_lazy_discord(self):
        from praisonai.bots import DiscordApproval
        assert DiscordApproval.__name__ == "DiscordApproval"

    def test_bots_init_lazy_webhook(self):
        from praisonai.bots import WebhookApproval
        assert WebhookApproval.__name__ == "WebhookApproval"

    def test_bots_init_lazy_http(self):
        from praisonai.bots import HTTPApproval
        assert HTTPApproval.__name__ == "HTTPApproval"

    def test_bots_init_unknown_raises(self):
        with pytest.raises((AttributeError, ImportError)):
            from praisonai.bots import NonExistentBackend  # noqa: F401
