"""
Tests for chat-native approval actor authorization.

Verifies that the per-channel approval backends (Telegram / Slack / Discord)
only honour an approve/deny from an authorised user when an
``allowed_approvers`` allowlist is configured, so an unauthorised member of a
shared group cannot resolve a gated tool. Legacy behaviour (no allowlist =
any actor) is preserved for backward compatibility.
"""

from __future__ import annotations

import asyncio

import pytest


def _make_request(**overrides):
    from praisonaiagents.approval.protocols import ApprovalRequest

    defaults = {
        "tool_name": "execute_command",
        "arguments": {"cmd": "rm -rf /"},
        "risk_level": "critical",
        "agent_name": "test-agent",
    }
    defaults.update(overrides)
    return ApprovalRequest(**defaults)


# ── Shared helper ────────────────────────────────────────────────────────────


class TestIsAuthorizedActor:
    def test_none_allowlist_permits_any_actor(self):
        from praisonai.bots._approval_base import is_authorized_actor

        assert is_authorized_actor("anyone", None) is True
        assert is_authorized_actor(None, None) is True

    def test_actor_in_allowlist_permitted(self):
        from praisonai.bots._approval_base import (
            is_authorized_actor,
            normalize_approvers,
        )

        allow = normalize_approvers(["999", "111"])
        assert is_authorized_actor("999", allow) is True

    def test_actor_not_in_allowlist_rejected(self):
        from praisonai.bots._approval_base import (
            is_authorized_actor,
            normalize_approvers,
        )

        allow = normalize_approvers(["999"])
        assert is_authorized_actor("123", allow) is False

    def test_none_actor_rejected_when_allowlist_set(self):
        from praisonai.bots._approval_base import (
            is_authorized_actor,
            normalize_approvers,
        )

        allow = normalize_approvers(["999"])
        assert is_authorized_actor(None, allow) is False

    def test_int_ids_normalized_to_str(self):
        from praisonai.bots._approval_base import (
            is_authorized_actor,
            normalize_approvers,
        )

        allow = normalize_approvers([999])
        assert is_authorized_actor("999", allow) is True


# ── Telegram ─────────────────────────────────────────────────────────────────


class TestTelegramAuthorization:
    def _backend(self, **kwargs):
        from praisonai.bots._telegram_approval import TelegramApproval

        return TelegramApproval(
            token="t", chat_id="123", timeout=1, poll_interval=0.05, **kwargs
        )

    def test_unauthorized_press_is_ignored(self):
        """A tap from a non-allowlisted user must NOT resolve the approval."""
        backend = self._backend(allowed_approvers=["999"])
        answered = []

        async def mock_api(method, payload, **kwargs):
            if method == "sendMessage":
                return {"ok": True, "result": {"message_id": 42}}
            if method == "getUpdates":
                return {
                    "ok": True,
                    "result": [{
                        "update_id": 100,
                        "callback_query": {
                            "id": "cb1",
                            "data": "approve",
                            "from": {"id": 555, "username": "intruder"},
                            "message": {"message_id": 42},
                        },
                    }],
                }
            if method == "answerCallbackQuery":
                answered.append(payload)
                return {"ok": True}
            return {"ok": True}

        backend._telegram_api = mock_api
        decision = asyncio.run(backend.request_approval(_make_request()))
        # Times out (stays gated) rather than approving.
        assert decision.approved is False
        assert "timed out" in decision.reason.lower()
        # The intruder was told they are not authorized.
        assert any(p.get("show_alert") for p in answered)

    def test_authorized_press_resolves(self):
        backend = self._backend(allowed_approvers=["999"])

        async def mock_api(method, payload, **kwargs):
            if method == "sendMessage":
                return {"ok": True, "result": {"message_id": 42}}
            if method == "getUpdates":
                return {
                    "ok": True,
                    "result": [{
                        "update_id": 100,
                        "callback_query": {
                            "id": "cb1",
                            "data": "approve",
                            "from": {"id": 999, "username": "owner"},
                            "message": {"message_id": 42},
                        },
                    }],
                }
            return {"ok": True}

        backend._telegram_api = mock_api
        decision = asyncio.run(backend.request_approval(_make_request()))
        assert decision.approved is True
        assert decision.approver == "999"

    def test_no_allowlist_permits_any_presser(self):
        """Backward compatible: without an allowlist, any presser resolves."""
        backend = self._backend()

        async def mock_api(method, payload, **kwargs):
            if method == "sendMessage":
                return {"ok": True, "result": {"message_id": 42}}
            if method == "getUpdates":
                return {
                    "ok": True,
                    "result": [{
                        "update_id": 100,
                        "callback_query": {
                            "id": "cb1",
                            "data": "approve",
                            "from": {"id": 555, "username": "anyone"},
                            "message": {"message_id": 42},
                        },
                    }],
                }
            return {"ok": True}

        backend._telegram_api = mock_api
        decision = asyncio.run(backend.request_approval(_make_request()))
        assert decision.approved is True

    def test_env_var_allowlist(self, monkeypatch):
        monkeypatch.setenv("TELEGRAM_APPROVERS", "999, 111")
        backend = self._backend()
        assert backend._allowed_approvers == {"999", "111"}


# ── Slack ────────────────────────────────────────────────────────────────────


class TestSlackAuthorization:
    def _backend(self, **kwargs):
        from praisonai.bots._slack_approval import SlackApproval

        return SlackApproval(
            token="xoxb-t", channel="C1", timeout=1, poll_interval=0.05, **kwargs
        )

    def test_unauthorized_reply_ignored(self):
        backend = self._backend(allowed_approvers=["U_OWNER"])

        async def mock_api(method, payload, **kwargs):
            if method == "chat.postMessage":
                return {"ok": True, "ts": "1.1", "channel": "C1"}
            if method in ("conversations.replies", "conversations.history"):
                return {
                    "ok": True,
                    "messages": [
                        {"ts": "2.2", "user": "U_INTRUDER", "text": "yes"},
                    ],
                }
            return {"ok": True}

        backend._slack_api = mock_api
        decision = asyncio.run(backend.request_approval(_make_request()))
        assert decision.approved is False
        assert "timed out" in decision.reason.lower()

    def test_authorized_reply_resolves(self):
        backend = self._backend(allowed_approvers=["U_OWNER"])

        async def mock_api(method, payload, **kwargs):
            if method == "chat.postMessage":
                return {"ok": True, "ts": "1.1", "channel": "C1"}
            if method in ("conversations.replies", "conversations.history"):
                return {
                    "ok": True,
                    "messages": [
                        {"ts": "2.2", "user": "U_OWNER", "text": "yes"},
                    ],
                }
            return {"ok": True}

        backend._slack_api = mock_api
        decision = asyncio.run(backend.request_approval(_make_request()))
        assert decision.approved is True
        assert decision.approver == "U_OWNER"

    def test_no_allowlist_permits_any_replier(self):
        backend = self._backend()

        async def mock_api(method, payload, **kwargs):
            if method == "chat.postMessage":
                return {"ok": True, "ts": "1.1", "channel": "C1"}
            if method in ("conversations.replies", "conversations.history"):
                return {
                    "ok": True,
                    "messages": [
                        {"ts": "2.2", "user": "U_ANYONE", "text": "yes"},
                    ],
                }
            return {"ok": True}

        backend._slack_api = mock_api
        decision = asyncio.run(backend.request_approval(_make_request()))
        assert decision.approved is True


# ── Discord ──────────────────────────────────────────────────────────────────


class TestDiscordAuthorization:
    def _backend(self, **kwargs):
        from praisonai.bots._discord_approval import DiscordApproval

        return DiscordApproval(
            token="t", channel_id="C1", timeout=1, poll_interval=0.05, **kwargs
        )

    def test_unauthorized_reply_ignored(self):
        backend = self._backend(allowed_approvers=["999"])

        async def mock_api(method, path, payload=None, **kwargs):
            if method == "POST" and path.endswith("/messages"):
                return {"id": "msg1"}
            if method == "GET":
                return [{
                    "id": "reply1",
                    "author": {"id": "555", "username": "intruder", "bot": False},
                    "content": "yes",
                    "message_reference": {"message_id": "msg1"},
                }]
            return {}

        backend._discord_api = mock_api
        decision = asyncio.run(backend.request_approval(_make_request()))
        assert decision.approved is False
        assert "timed out" in decision.reason.lower()

    def test_authorized_reply_resolves(self):
        backend = self._backend(allowed_approvers=["999"])

        async def mock_api(method, path, payload=None, **kwargs):
            if method == "POST" and path.endswith("/messages"):
                return {"id": "msg1"}
            if method == "GET":
                return [{
                    "id": "reply1",
                    "author": {"id": "999", "username": "owner", "bot": False},
                    "content": "yes",
                    "message_reference": {"message_id": "msg1"},
                }]
            return {}

        backend._discord_api = mock_api
        decision = asyncio.run(backend.request_approval(_make_request()))
        assert decision.approved is True
        assert decision.approver == "999"

    def test_no_allowlist_permits_any_replier(self):
        backend = self._backend()

        async def mock_api(method, path, payload=None, **kwargs):
            if method == "POST" and path.endswith("/messages"):
                return {"id": "msg1"}
            if method == "GET":
                return [{
                    "id": "reply1",
                    "author": {"id": "555", "username": "anyone", "bot": False},
                    "content": "yes",
                    "message_reference": {"message_id": "msg1"},
                }]
            return {}

        backend._discord_api = mock_api
        decision = asyncio.run(backend.request_approval(_make_request()))
        assert decision.approved is True
