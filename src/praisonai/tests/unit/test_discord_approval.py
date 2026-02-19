"""
TDD tests for DiscordApproval backend.

Tests the Discord-based approval backend that sends embeds via REST API
and polls for text-reply responses.
"""

from __future__ import annotations

import asyncio

import pytest


# ── Protocol Conformance ────────────────────────────────────────────────────


class TestDiscordApprovalProtocol:
    def test_conforms_to_approval_protocol(self):
        from praisonaiagents.approval.protocols import ApprovalProtocol
        from praisonai.bots._discord_approval import DiscordApproval

        backend = DiscordApproval(token="fake-token", channel_id="123")
        assert isinstance(backend, ApprovalProtocol)

    def test_has_request_approval_sync(self):
        from praisonai.bots._discord_approval import DiscordApproval

        backend = DiscordApproval(token="fake-token", channel_id="123")
        assert hasattr(backend, "request_approval_sync")

    def test_has_request_approval_async(self):
        from praisonai.bots._discord_approval import DiscordApproval

        backend = DiscordApproval(token="fake-token", channel_id="123")
        assert asyncio.iscoroutinefunction(backend.request_approval)


# ── Construction & Config ───────────────────────────────────────────────────


class TestDiscordApprovalInit:
    def test_explicit_token(self):
        from praisonai.bots._discord_approval import DiscordApproval

        backend = DiscordApproval(token="my-token", channel_id="123")
        assert backend._token == "my-token"

    def test_env_var_token(self, monkeypatch):
        monkeypatch.setenv("DISCORD_BOT_TOKEN", "env-token")
        from praisonai.bots._discord_approval import DiscordApproval

        backend = DiscordApproval(channel_id="123")
        assert backend._token == "env-token"

    def test_missing_token_raises(self, monkeypatch):
        monkeypatch.delenv("DISCORD_BOT_TOKEN", raising=False)
        from praisonai.bots._discord_approval import DiscordApproval

        with pytest.raises(ValueError, match="[Tt]oken"):
            DiscordApproval(channel_id="123")

    def test_repr_masks_token(self):
        from praisonai.bots._discord_approval import DiscordApproval

        backend = DiscordApproval(token="super-secret-token", channel_id="99")
        r = repr(backend)
        assert "super-secret-token" not in r
        assert "99" in r

    def test_env_var_channel_id(self, monkeypatch):
        monkeypatch.setenv("DISCORD_CHANNEL_ID", "env-chan-123")
        from praisonai.bots._discord_approval import DiscordApproval

        backend = DiscordApproval(token="t")
        assert backend._channel_id == "env-chan-123"

    def test_ssl_verify_default_true(self, monkeypatch):
        monkeypatch.delenv("PRAISONAI_DISCORD_SSL_VERIFY", raising=False)
        from praisonai.bots._discord_approval import DiscordApproval

        backend = DiscordApproval(token="t", channel_id="1")
        assert backend._ssl_verify is True

    def test_ssl_verify_env_false(self, monkeypatch):
        monkeypatch.setenv("PRAISONAI_DISCORD_SSL_VERIFY", "false")
        from praisonai.bots._discord_approval import DiscordApproval

        backend = DiscordApproval(token="t", channel_id="1")
        assert backend._ssl_verify is False


# ── Embed Builder ───────────────────────────────────────────────────────────


class TestEmbedBuilder:
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

    def test_embed_contains_tool_name(self):
        from praisonai.bots._discord_approval import DiscordApproval

        backend = DiscordApproval(token="t", channel_id="123")
        embed = backend._build_embed(self._make_request(tool_name="rm_file"))
        fields_str = str(embed.get("fields", []))
        assert "rm_file" in fields_str

    def test_embed_has_color(self):
        from praisonai.bots._discord_approval import DiscordApproval

        backend = DiscordApproval(token="t", channel_id="123")
        embed = backend._build_embed(self._make_request(risk_level="critical"))
        assert "color" in embed
        assert embed["color"] == 0xFF0000

    def test_fallback_text(self):
        from praisonai.bots._discord_approval import DiscordApproval

        backend = DiscordApproval(token="t", channel_id="123")
        text = backend._build_fallback_text(self._make_request())
        assert "execute_command" in text


# ── Async Approval Flow ────────────────────────────────────────────────────


class TestApprovalFlowAsync:
    def _make_request(self, **overrides):
        from praisonaiagents.approval.protocols import ApprovalRequest

        defaults = {
            "tool_name": "execute_command",
            "arguments": {"cmd": "ls"},
            "risk_level": "high",
            "agent_name": "test-agent",
        }
        defaults.update(overrides)
        return ApprovalRequest(**defaults)

    def test_approved_via_text_reply(self):
        from praisonai.bots._discord_approval import DiscordApproval

        backend = DiscordApproval(token="t", channel_id="123", timeout=5, poll_interval=0.1)
        poll_count = {"n": 0}

        async def mock_api(method, path, payload=None, **kwargs):
            if "messages" in path and method == "POST":
                return {"id": "msg123"}
            if "messages" in path and method == "GET":
                poll_count["n"] += 1
                if poll_count["n"] <= 1:
                    return []
                return [
                    {"content": "yes", "author": {"id": "u1", "username": "tester", "bot": False}, "id": "r1"},
                ]
            return {}

        async def mock_update(*a, **kw):
            pass

        backend._discord_api = mock_api
        backend._update_message = mock_update
        decision = asyncio.run(backend.request_approval(self._make_request()))
        assert decision.approved is True
        assert decision.approver == "u1"

    def test_denied_via_text_reply(self):
        from praisonai.bots._discord_approval import DiscordApproval

        backend = DiscordApproval(token="t", channel_id="123", timeout=5, poll_interval=0.1)

        async def mock_api(method, path, payload=None, **kwargs):
            if "messages" in path and method == "POST":
                return {"id": "msg123"}
            if "messages" in path and method == "GET":
                return [
                    {"content": "deny", "author": {"id": "u1", "username": "tester", "bot": False}, "id": "r1"},
                ]
            return {}

        async def mock_update(*a, **kw):
            pass

        backend._discord_api = mock_api
        backend._update_message = mock_update
        decision = asyncio.run(backend.request_approval(self._make_request()))
        assert decision.approved is False

    def test_timeout_returns_denial(self):
        from praisonai.bots._discord_approval import DiscordApproval

        backend = DiscordApproval(token="t", channel_id="123", timeout=0.5, poll_interval=0.1)

        async def mock_api(method, path, payload=None, **kwargs):
            if "messages" in path and method == "POST":
                return {"id": "msg123"}
            if "messages" in path and method == "GET":
                return []
            return {}

        async def mock_update(*a, **kw):
            pass

        backend._discord_api = mock_api
        backend._update_message = mock_update
        decision = asyncio.run(backend.request_approval(self._make_request()))
        assert decision.approved is False
        assert "timeout" in decision.reason.lower() or "timed out" in decision.reason.lower()

    def test_post_failure_returns_denial(self):
        from praisonai.bots._discord_approval import DiscordApproval

        backend = DiscordApproval(token="t", channel_id="123", timeout=5, poll_interval=0.1)

        async def mock_api(method, path, payload=None, **kwargs):
            if "messages" in path and method == "POST":
                return {"message": "Missing Permissions"}
            return {}

        backend._discord_api = mock_api
        decision = asyncio.run(backend.request_approval(self._make_request()))
        assert decision.approved is False

    def test_no_channel_returns_denial(self):
        from praisonai.bots._discord_approval import DiscordApproval

        backend = DiscordApproval(token="t", channel_id="", timeout=2, poll_interval=0.1)
        decision = asyncio.run(backend.request_approval(self._make_request()))
        assert decision.approved is False
        assert "channel_id" in decision.reason.lower()

    def test_skips_bot_messages(self):
        from praisonai.bots._discord_approval import DiscordApproval

        backend = DiscordApproval(token="t", channel_id="123", timeout=1, poll_interval=0.1)
        poll_count = {"n": 0}

        async def mock_api(method, path, payload=None, **kwargs):
            if "messages" in path and method == "POST":
                return {"id": "msg123"}
            if "messages" in path and method == "GET":
                poll_count["n"] += 1
                if poll_count["n"] <= 2:
                    return [{"content": "yes", "author": {"id": "b1", "bot": True}, "id": "r1"}]
                return [{"content": "yes", "author": {"id": "u1", "username": "human", "bot": False}, "id": "r2"}]
            return {}

        async def mock_update(*a, **kw):
            pass

        backend._discord_api = mock_api
        backend._update_message = mock_update
        decision = asyncio.run(backend.request_approval(self._make_request()))
        assert decision.approved is True


# ── Export / Import ─────────────────────────────────────────────────────────


class TestExports:
    def test_import_from_bots_package(self):
        from praisonai.bots import DiscordApproval
        assert DiscordApproval is not None

    def test_import_directly(self):
        from praisonai.bots._discord_approval import DiscordApproval
        assert DiscordApproval is not None
