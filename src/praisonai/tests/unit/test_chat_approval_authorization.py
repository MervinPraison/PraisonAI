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

    def test_comma_separated_string_normalized(self):
        from praisonai.bots._approval_base import normalize_approvers

        assert normalize_approvers("999,111") == {"999", "111"}
        assert normalize_approvers("999, 111 ") == {"999", "111"}


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
                            "message": {"message_id": 42, "chat": {"id": 123}},
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
                            "message": {"message_id": 42, "chat": {"id": 123}},
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
                            "message": {"message_id": 42, "chat": {"id": 123}},
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

    def test_callback_from_different_chat_ignored(self):
        """A tap on a same-message_id button in a DIFFERENT chat must not resolve."""
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
                            "message": {"message_id": 42, "chat": {"id": 999999}},
                        },
                    }],
                }
            return {"ok": True}

        backend._telegram_api = mock_api
        decision = asyncio.run(backend.request_approval(_make_request()))
        assert decision.approved is False
        assert "timed out" in decision.reason.lower()


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


# ── HTTP dashboard (out-of-band) ─────────────────────────────────────────────


class TestHTTPAuthorization:
    def _backend(self, **kwargs):
        from praisonai.bots._http_approval import HTTPApproval

        backend = HTTPApproval(port=0, timeout=1, **kwargs)

        async def mock_server():
            backend._server_started = True

        backend._ensure_server = mock_server
        return backend

    def test_no_allowlist_mints_no_token(self):
        """Legacy: no allowlist → no token on the pending approval."""
        backend = self._backend()

        async def run():
            async def simulate():
                await asyncio.sleep(0.2)
                for info in backend._pending.values():
                    assert info.get("token") is None
                    info["decided"] = True
                    info["approved"] = True
                    info["approver"] = "anyone"
                    break

            task = asyncio.create_task(simulate())
            decision = await backend.request_approval(_make_request())
            await task
            return decision

        decision = asyncio.run(run())
        assert decision.approved is True

    def test_allowlist_mints_token(self):
        """With an allowlist a single-use token is bound to the approval."""
        backend = self._backend(allowed_approvers=["owner"])

        async def run():
            async def simulate():
                await asyncio.sleep(0.2)
                for info in backend._pending.values():
                    assert info.get("token")
                    info["decided"] = True
                    info["approved"] = True
                    info["approver"] = "owner"
                    break

            task = asyncio.create_task(simulate())
            decision = await backend.request_approval(_make_request())
            await task
            return decision

        decision = asyncio.run(run())
        assert decision.approved is True

    def test_decide_without_token_rejected(self):
        """A POST lacking the per-approval token is refused (403)."""
        backend = self._backend(allowed_approvers=["owner"])
        backend._pending["r1"] = {
            "decided": False, "approved": False, "token": "secret-tok", "info": {},
        }

        class _Req:
            match_info = {"request_id": "r1"}
            query: dict = {}
            headers: dict = {}

            async def json(self):
                return {"decision": "approve", "approver": "owner"}

        resp = asyncio.run(backend._handle_decide(_Req()))
        assert resp.status == 403
        assert backend._pending["r1"]["decided"] is False

    def test_decide_with_token_but_unauthorized_approver_rejected(self):
        """Correct token but approver not in allowlist is refused."""
        backend = self._backend(allowed_approvers=["owner"])
        backend._pending["r1"] = {
            "decided": False, "approved": False, "token": "secret-tok", "info": {},
        }

        class _Req:
            match_info = {"request_id": "r1"}
            query = {"token": "secret-tok"}
            headers: dict = {}

            async def json(self):
                return {"decision": "approve", "approver": "intruder"}

        resp = asyncio.run(backend._handle_decide(_Req()))
        assert resp.status == 403
        assert backend._pending["r1"]["decided"] is False

    def test_decide_with_token_and_authorized_approver_resolves(self):
        backend = self._backend(allowed_approvers=["owner"])
        backend._pending["r1"] = {
            "decided": False, "approved": False, "token": "secret-tok", "info": {},
        }

        class _Req:
            match_info = {"request_id": "r1"}
            query = {"token": "secret-tok"}
            headers: dict = {}

            async def json(self):
                return {"decision": "approve", "approver": "owner"}

        resp = asyncio.run(backend._handle_decide(_Req()))
        assert resp.status == 200
        assert backend._pending["r1"]["decided"] is True
        assert backend._pending["r1"]["approved"] is True
        assert backend._pending["r1"]["approver"] == "owner"

    def test_dashboard_button_without_approver_resolves_via_token(self):
        """The dashboard buttons POST only the decision (no free-text
        approver). A valid token must still resolve, pinning the recorded
        approver to the allowlist — regression guard for the 403 that would
        otherwise strand the real approver's click until timeout."""
        backend = self._backend(allowed_approvers=["owner"])
        backend._pending["r1"] = {
            "decided": False, "approved": False, "token": "secret-tok", "info": {},
        }

        class _Req:
            match_info = {"request_id": "r1"}
            query = {"token": "secret-tok"}
            headers: dict = {}

            async def json(self):
                return {"decision": "approve"}

        resp = asyncio.run(backend._handle_decide(_Req()))
        assert resp.status == 200
        assert backend._pending["r1"]["decided"] is True
        assert backend._pending["r1"]["approved"] is True
        # Identity pinned to the allowlist rather than the legacy "http_user".
        assert backend._pending["r1"]["approver"] == "owner"

    def test_token_not_written_to_logs(self, caplog):
        """The single-use token must never appear in the general logs
        (regression guard: a log reader could otherwise lift the token)."""
        import logging

        backend = self._backend(allowed_approvers=["owner"])

        async def run():
            async def simulate():
                await asyncio.sleep(0.2)
                for info in backend._pending.values():
                    info["decided"] = True
                    info["approved"] = True
                    info["approver"] = "owner"
                    break

            task = asyncio.create_task(simulate())
            with caplog.at_level(logging.INFO, logger="praisonai_bot.bots._http_approval"):
                decision = await backend.request_approval(_make_request())
            await task
            return decision

        decision = asyncio.run(run())
        assert decision.approved is True
        token = decision.metadata.get("token")  # not surfaced in metadata
        assert token is None
        for record in caplog.records:
            assert "token=" not in record.getMessage()

    def test_store_cannot_be_passed_positionally(self):
        """``allowed_approvers``/``store`` are keyword-only so a legacy
        positional ``store`` can't be mis-bound to the allowlist."""
        from praisonai.bots._http_approval import HTTPApproval

        with pytest.raises(TypeError):
            HTTPApproval("127.0.0.1", 8899, 1.0, object())  # noqa: positional store


# ── Webhook (out-of-band) ────────────────────────────────────────────────────


class TestWebhookAuthorization:
    def _backend(self, **kwargs):
        from praisonai.bots._webhook_approval import WebhookApproval

        return WebhookApproval(
            webhook_url="https://example.com", timeout=1, poll_interval=0.05, **kwargs
        )

    def test_unauthorized_immediate_decision_dropped(self):
        """Immediate POST approval from a non-allowlisted approver is dropped."""
        backend = self._backend(allowed_approvers=["owner"])

        async def mock_http(method, url, payload=None, **kwargs):
            if method == "POST":
                return {"approved": True, "approver": "intruder"}
            return {"status": "pending"}

        backend._http_request = mock_http
        decision = asyncio.run(backend.request_approval(_make_request()))
        assert decision.approved is False
        assert "timed out" in decision.reason.lower()

    def test_authorized_immediate_decision_resolves(self):
        backend = self._backend(allowed_approvers=["owner"])

        async def mock_http(method, url, payload=None, **kwargs):
            if method == "POST":
                return {"approved": True, "approver": "owner"}
            return {"status": "pending"}

        backend._http_request = mock_http
        decision = asyncio.run(backend.request_approval(_make_request()))
        assert decision.approved is True
        assert decision.approver == "owner"

    def test_unauthorized_poll_decision_dropped(self):
        backend = self._backend(allowed_approvers=["owner"])

        async def mock_http(method, url, payload=None, **kwargs):
            if method == "POST":
                return {"status": "pending"}
            if method == "GET":
                return {"status": "approved", "approver": "intruder"}
            return {}

        backend._http_request = mock_http
        decision = asyncio.run(backend.request_approval(_make_request()))
        assert decision.approved is False
        assert "timed out" in decision.reason.lower()

    def test_authorized_poll_decision_resolves(self):
        backend = self._backend(allowed_approvers=["owner"])

        async def mock_http(method, url, payload=None, **kwargs):
            if method == "POST":
                return {"status": "pending"}
            if method == "GET":
                return {"approved": True, "approver": "owner"}
            return {}

        backend._http_request = mock_http
        decision = asyncio.run(backend.request_approval(_make_request()))
        assert decision.approved is True
        assert decision.approver == "owner"

    def test_no_allowlist_permits_any_approver(self):
        """Backward compatible: without an allowlist, any approver resolves."""
        backend = self._backend()

        async def mock_http(method, url, payload=None, **kwargs):
            if method == "POST":
                return {"approved": True, "approver": "anyone"}
            return {}

        backend._http_request = mock_http
        decision = asyncio.run(backend.request_approval(_make_request()))
        assert decision.approved is True

    def test_env_var_allowlist(self, monkeypatch):
        monkeypatch.setenv("WEBHOOK_APPROVERS", "owner, boss")
        backend = self._backend()
        assert backend._allowed_approvers == {"owner", "boss"}
