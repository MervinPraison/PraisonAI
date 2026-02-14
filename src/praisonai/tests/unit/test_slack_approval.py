"""
TDD tests for SlackApproval backend.

Tests the Slack-based approval backend that sends Block Kit messages
to Slack and waits for user response via polling.
"""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, patch

import pytest


# ── Protocol Conformance ────────────────────────────────────────────────────


class TestSlackApprovalProtocol:
    """SlackApproval must satisfy ApprovalProtocol."""

    def test_conforms_to_approval_protocol(self):
        from praisonaiagents.approval.protocols import ApprovalProtocol
        from praisonai.bots._slack_approval import SlackApproval

        backend = SlackApproval(token="xoxb-fake", channel="C123")
        assert isinstance(backend, ApprovalProtocol)

    def test_has_request_approval_sync(self):
        from praisonai.bots._slack_approval import SlackApproval

        backend = SlackApproval(token="xoxb-fake", channel="C123")
        assert hasattr(backend, "request_approval_sync")
        assert callable(backend.request_approval_sync)

    def test_has_request_approval_async(self):
        from praisonai.bots._slack_approval import SlackApproval

        backend = SlackApproval(token="xoxb-fake", channel="C123")
        assert hasattr(backend, "request_approval")
        assert asyncio.iscoroutinefunction(backend.request_approval)


# ── Construction & Config ───────────────────────────────────────────────────


class TestSlackApprovalInit:
    def test_explicit_token(self):
        from praisonai.bots._slack_approval import SlackApproval

        backend = SlackApproval(token="xoxb-test", channel="C123")
        assert backend._token == "xoxb-test"
        assert backend._channel == "C123"

    def test_env_var_token(self, monkeypatch):
        monkeypatch.setenv("SLACK_BOT_TOKEN", "xoxb-from-env")
        from praisonai.bots._slack_approval import SlackApproval

        backend = SlackApproval(channel="C123")
        assert backend._token == "xoxb-from-env"

    def test_missing_token_raises(self, monkeypatch):
        monkeypatch.delenv("SLACK_BOT_TOKEN", raising=False)
        from praisonai.bots._slack_approval import SlackApproval

        with pytest.raises(ValueError, match="[Tt]oken"):
            SlackApproval(channel="C123")

    def test_default_timeout(self):
        from praisonai.bots._slack_approval import SlackApproval

        backend = SlackApproval(token="xoxb-test", channel="C123")
        assert backend._timeout == 300  # 5 minutes

    def test_custom_timeout(self):
        from praisonai.bots._slack_approval import SlackApproval

        backend = SlackApproval(token="xoxb-test", channel="C123", timeout=60)
        assert backend._timeout == 60

    def test_default_poll_interval(self):
        from praisonai.bots._slack_approval import SlackApproval

        backend = SlackApproval(token="xoxb-test", channel="C123")
        assert backend._poll_interval == 3.0

    def test_custom_poll_interval(self):
        from praisonai.bots._slack_approval import SlackApproval

        backend = SlackApproval(token="xoxb-test", channel="C123", poll_interval=1.0)
        assert backend._poll_interval == 1.0


# ── Block Kit Message Builder ───────────────────────────────────────────────


class TestBlockKitBuilder:
    def _make_request(self, **overrides):
        from praisonaiagents.approval.protocols import ApprovalRequest

        defaults = {
            "tool_name": "execute_command",
            "arguments": {"cmd": "ls -la"},
            "risk_level": "critical",
            "agent_name": "test-agent",
        }
        defaults.update(overrides)
        return ApprovalRequest(**defaults)

    def test_builds_valid_blocks(self):
        from praisonai.bots._slack_approval import SlackApproval

        backend = SlackApproval(token="xoxb-test", channel="C123")
        request = self._make_request()
        blocks = backend._build_blocks(request)

        assert isinstance(blocks, list)
        assert len(blocks) >= 2  # At least header section + context

    def test_blocks_contain_tool_name(self):
        from praisonai.bots._slack_approval import SlackApproval

        backend = SlackApproval(token="xoxb-test", channel="C123")
        request = self._make_request(tool_name="delete_file")
        blocks = backend._build_blocks(request)
        blocks_json = json.dumps(blocks)
        assert "delete_file" in blocks_json

    def test_blocks_contain_risk_level(self):
        from praisonai.bots._slack_approval import SlackApproval

        backend = SlackApproval(token="xoxb-test", channel="C123")
        request = self._make_request(risk_level="high")
        blocks = backend._build_blocks(request)
        blocks_json = json.dumps(blocks)
        assert "HIGH" in blocks_json or "high" in blocks_json.lower()

    def test_blocks_contain_agent_name(self):
        from praisonai.bots._slack_approval import SlackApproval

        backend = SlackApproval(token="xoxb-test", channel="C123")
        request = self._make_request(agent_name="my-bot")
        blocks = backend._build_blocks(request)
        blocks_json = json.dumps(blocks)
        assert "my-bot" in blocks_json

    def test_blocks_contain_arguments(self):
        from praisonai.bots._slack_approval import SlackApproval

        backend = SlackApproval(token="xoxb-test", channel="C123")
        request = self._make_request(arguments={"cmd": "rm -rf /tmp"})
        blocks = backend._build_blocks(request)
        blocks_json = json.dumps(blocks)
        assert "rm -rf /tmp" in blocks_json

    def test_fallback_text(self):
        from praisonai.bots._slack_approval import SlackApproval

        backend = SlackApproval(token="xoxb-test", channel="C123")
        request = self._make_request()
        text = backend._build_fallback_text(request)
        assert "execute_command" in text
        assert "yes" in text.lower() or "approve" in text.lower()


# ── Async Approval Flow (Mocked _slack_api) ────────────────────────────────


class TestApprovalFlowAsync:
    """Test the full approval flow by mocking _slack_api."""

    def _make_request(self, **overrides):
        from praisonaiagents.approval.protocols import ApprovalRequest

        defaults = {
            "tool_name": "execute_command",
            "arguments": {"cmd": "ls"},
            "risk_level": "critical",
            "agent_name": "test-agent",
        }
        defaults.update(overrides)
        return ApprovalRequest(**defaults)

    def test_approved_via_reply(self):
        """Polling finds 'yes' reply → approved."""
        from praisonai.bots._slack_approval import SlackApproval

        backend = SlackApproval(token="xoxb-test", channel="C123", timeout=5, poll_interval=0.1)

        poll_count = {"n": 0}

        async def mock_api(method, payload, **kwargs):
            if method == "chat.postMessage":
                return {"ok": True, "ts": "1234.5678", "channel": "C123"}
            if method in ("conversations.replies", "conversations.history"):
                poll_count["n"] += 1
                if poll_count["n"] <= 1:
                    return {"ok": True, "messages": []}
                return {
                    "ok": True,
                    "messages": [{"text": "yes", "user": "U999", "ts": "1234.9999"}],
                }
            if method == "chat.update":
                return {"ok": True}
            return {"ok": True}

        backend._slack_api = mock_api
        request = self._make_request()
        decision = asyncio.run(backend.request_approval(request))

        assert decision.approved is True
        assert decision.approver == "U999"

    def test_denied_via_reply(self):
        """Polling finds 'no' reply → denied."""
        from praisonai.bots._slack_approval import SlackApproval

        backend = SlackApproval(token="xoxb-test", channel="C123", timeout=5, poll_interval=0.1)

        async def mock_api(method, payload, **kwargs):
            if method == "chat.postMessage":
                return {"ok": True, "ts": "1234.5678", "channel": "C123"}
            if method in ("conversations.replies", "conversations.history"):
                return {
                    "ok": True,
                    "messages": [{"text": "no", "user": "U999", "ts": "1234.9999"}],
                }
            if method == "chat.update":
                return {"ok": True}
            return {"ok": True}

        backend._slack_api = mock_api
        request = self._make_request()
        decision = asyncio.run(backend.request_approval(request))

        assert decision.approved is False
        assert decision.approver == "U999"

    def test_timeout_returns_denial(self):
        """No response within timeout → auto-deny."""
        from praisonai.bots._slack_approval import SlackApproval

        backend = SlackApproval(token="xoxb-test", channel="C123", timeout=0.5, poll_interval=0.1)

        async def mock_api(method, payload, **kwargs):
            if method == "chat.postMessage":
                return {"ok": True, "ts": "1234.5678", "channel": "C123"}
            if method in ("conversations.replies", "conversations.history"):
                return {"ok": True, "messages": []}
            if method == "chat.update":
                return {"ok": True}
            return {"ok": True}

        backend._slack_api = mock_api
        request = self._make_request()
        decision = asyncio.run(backend.request_approval(request))

        assert decision.approved is False
        assert "timeout" in decision.reason.lower() or "timed out" in decision.reason.lower()

    def test_message_updated_after_approval(self):
        """After approval, chat.update is called."""
        from praisonai.bots._slack_approval import SlackApproval

        backend = SlackApproval(token="xoxb-test", channel="C123", timeout=5, poll_interval=0.1)

        update_calls = []

        async def mock_api(method, payload, **kwargs):
            if method == "chat.postMessage":
                return {"ok": True, "ts": "1234.5678", "channel": "C123"}
            if method in ("conversations.replies", "conversations.history"):
                return {
                    "ok": True,
                    "messages": [{"text": "yes", "user": "U999", "ts": "1234.9999"}],
                }
            if method == "chat.update":
                update_calls.append(payload)
                return {"ok": True}
            return {"ok": True}

        backend._slack_api = mock_api
        request = self._make_request()
        asyncio.run(backend.request_approval(request))

        assert len(update_calls) == 1
        assert "1234.5678" in str(update_calls[0].get("ts", ""))

    def test_skips_bot_own_message_in_poll(self):
        """Polling skips the bot's own approval message ts."""
        from praisonai.bots._slack_approval import SlackApproval

        backend = SlackApproval(token="xoxb-test", channel="C123", timeout=1, poll_interval=0.1)

        poll_count = {"n": 0}

        async def mock_api(method, payload, **kwargs):
            if method == "chat.postMessage":
                return {"ok": True, "ts": "1234.5678", "channel": "C123"}
            if method in ("conversations.replies", "conversations.history"):
                poll_count["n"] += 1
                if poll_count["n"] <= 2:
                    return {
                        "ok": True,
                        "messages": [{"text": "yes", "ts": "1234.5678", "bot_id": "B123"}],
                    }
                return {
                    "ok": True,
                    "messages": [{"text": "approve", "user": "U999", "ts": "1234.9999"}],
                }
            if method == "chat.update":
                return {"ok": True}
            return {"ok": True}

        backend._slack_api = mock_api
        request = self._make_request()
        decision = asyncio.run(backend.request_approval(request))

        assert decision.approved is True

    def test_post_failure_returns_denial(self):
        """If chat.postMessage fails, return denial immediately."""
        from praisonai.bots._slack_approval import SlackApproval

        backend = SlackApproval(token="xoxb-test", channel="C123", timeout=5, poll_interval=0.1)

        async def mock_api(method, payload, **kwargs):
            if method == "chat.postMessage":
                return {"ok": False, "error": "channel_not_found"}
            return {"ok": True}

        backend._slack_api = mock_api
        request = self._make_request()
        decision = asyncio.run(backend.request_approval(request))

        assert decision.approved is False
        assert "channel_not_found" in decision.reason

    def test_no_channel_resolves_from_auth(self):
        """If no channel set, resolves via auth.test."""
        from praisonai.bots._slack_approval import SlackApproval

        backend = SlackApproval(token="xoxb-test", channel="", timeout=2, poll_interval=0.1)

        async def mock_api(method, payload, **kwargs):
            if method == "auth.test":
                return {"ok": True, "user_id": "U_RESOLVED"}
            if method == "chat.postMessage":
                assert payload["channel"] == "U_RESOLVED"
                return {"ok": True, "ts": "1234.5678", "channel": "U_RESOLVED"}
            if method in ("conversations.replies", "conversations.history"):
                return {
                    "ok": True,
                    "messages": [{"text": "yes", "user": "U999", "ts": "1234.9999"}],
                }
            if method == "chat.update":
                return {"ok": True}
            return {"ok": True}

        backend._slack_api = mock_api
        request = self._make_request()
        decision = asyncio.run(backend.request_approval(request))

        assert decision.approved is True

    def test_thread_replies_used_for_isolation(self):
        """conversations.replies is called with ts= for thread isolation."""
        from praisonai.bots._slack_approval import SlackApproval

        backend = SlackApproval(token="xoxb-test", channel="C123", timeout=5, poll_interval=0.1)
        api_calls = []

        async def mock_api(method, payload, **kwargs):
            api_calls.append((method, payload))
            if method == "chat.postMessage":
                return {"ok": True, "ts": "1234.5678", "channel": "C123"}
            if method == "conversations.replies":
                return {
                    "ok": True,
                    "messages": [
                        {"ts": "1234.5678", "bot_id": "B1"},
                        {"text": "yes", "user": "U999", "ts": "1234.9999"},
                    ],
                }
            if method == "chat.update":
                return {"ok": True}
            return {"ok": True}

        backend._slack_api = mock_api
        request = self._make_request()
        decision = asyncio.run(backend.request_approval(request))

        assert decision.approved is True
        replies_calls = [c for c in api_calls if c[0] == "conversations.replies"]
        assert len(replies_calls) >= 1
        assert replies_calls[0][1]["ts"] == "1234.5678"

    def test_falls_back_to_history_if_replies_fails(self):
        """If conversations.replies fails, falls back to conversations.history."""
        from praisonai.bots._slack_approval import SlackApproval

        backend = SlackApproval(token="xoxb-test", channel="C123", timeout=5, poll_interval=0.1)

        async def mock_api(method, payload, **kwargs):
            if method == "chat.postMessage":
                return {"ok": True, "ts": "1234.5678", "channel": "C123"}
            if method == "conversations.replies":
                return {"ok": False, "error": "method_not_allowed"}
            if method == "conversations.history":
                return {
                    "ok": True,
                    "messages": [{"text": "yes", "user": "U999", "ts": "1234.9999"}],
                }
            if method == "chat.update":
                return {"ok": True}
            return {"ok": True}

        backend._slack_api = mock_api
        request = self._make_request()
        decision = asyncio.run(backend.request_approval(request))

        assert decision.approved is True


# ── Sync Wrapper ────────────────────────────────────────────────────────────


class TestSyncWrapper:
    def test_request_approval_sync_delegates(self):
        """request_approval_sync wraps the async method."""
        from praisonai.bots._slack_approval import SlackApproval
        from praisonaiagents.approval.protocols import ApprovalRequest, ApprovalDecision

        backend = SlackApproval(token="xoxb-test", channel="C123")
        expected = ApprovalDecision(approved=True, reason="test")

        with patch.object(backend, "request_approval", new_callable=AsyncMock, return_value=expected):
            req = ApprovalRequest(tool_name="x", arguments={}, risk_level="low")
            result = backend.request_approval_sync(req)
            assert result.approved is True


# ── Agent Integration ───────────────────────────────────────────────────────


class TestAgentIntegration:
    def test_agent_accepts_slack_approval(self):
        """Agent(approval=SlackApproval(...)) stores the backend."""
        from praisonaiagents import Agent
        from praisonai.bots._slack_approval import SlackApproval

        backend = SlackApproval(token="xoxb-test", channel="C123")
        agent = Agent(name="test", instructions="test", approval=backend)
        assert agent._approval_backend is backend

    def test_agent_uses_slack_approval_in_tool_exec(self):
        """Agent with SlackApproval uses it for dangerous tool approval."""
        from praisonaiagents import Agent
        from praisonai.bots._slack_approval import SlackApproval
        from praisonaiagents.approval.protocols import ApprovalDecision

        call_log = []

        class MockSlackApproval(SlackApproval):
            def __init__(self):
                self._token = "xoxb-fake"
                self._channel = "C123"
                self._timeout = 300
                self._poll_interval = 3.0

            def request_approval_sync(self, request):
                call_log.append(request.tool_name)
                return ApprovalDecision(approved=True, reason="slack-approved", approver="U999")

            async def request_approval(self, request):
                return ApprovalDecision(approved=True, reason="slack-approved", approver="U999")

        def execute_command(cmd: str) -> str:
            """Execute a command."""
            return f"ran: {cmd}"

        backend = MockSlackApproval()
        agent = Agent(name="test", instructions="test", tools=[execute_command], approval=backend)
        result = agent._execute_tool_impl("execute_command", {"cmd": "ls"})
        assert "execute_command" in call_log
        assert result == "ran: ls"


# ── Export / Import ─────────────────────────────────────────────────────────


class TestExports:
    def test_import_from_bots_package(self):
        from praisonai.bots import SlackApproval
        assert SlackApproval is not None

    def test_import_directly(self):
        from praisonai.bots._slack_approval import SlackApproval
        assert SlackApproval is not None
