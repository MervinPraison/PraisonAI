"""
TDD tests for TelegramApproval backend.

Tests the Telegram-based approval backend that sends inline keyboard
messages and polls getUpdates for callback_query responses.
"""

from __future__ import annotations

import asyncio
import json

import pytest


# ── Protocol Conformance ────────────────────────────────────────────────────


class TestTelegramApprovalProtocol:
    def test_conforms_to_approval_protocol(self):
        from praisonaiagents.approval.protocols import ApprovalProtocol
        from praisonai.bots._telegram_approval import TelegramApproval

        backend = TelegramApproval(token="fake-token", chat_id="123")
        assert isinstance(backend, ApprovalProtocol)

    def test_has_request_approval_sync(self):
        from praisonai.bots._telegram_approval import TelegramApproval

        backend = TelegramApproval(token="fake-token", chat_id="123")
        assert hasattr(backend, "request_approval_sync")
        assert callable(backend.request_approval_sync)

    def test_has_request_approval_async(self):
        from praisonai.bots._telegram_approval import TelegramApproval

        backend = TelegramApproval(token="fake-token", chat_id="123")
        assert hasattr(backend, "request_approval")
        assert asyncio.iscoroutinefunction(backend.request_approval)


# ── Construction & Config ───────────────────────────────────────────────────


class TestTelegramApprovalInit:
    def test_explicit_token(self):
        from praisonai.bots._telegram_approval import TelegramApproval

        backend = TelegramApproval(token="my-token", chat_id="123")
        assert backend._token == "my-token"
        assert backend._chat_id == "123"

    def test_env_var_token(self, monkeypatch):
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "env-token")
        from praisonai.bots._telegram_approval import TelegramApproval

        backend = TelegramApproval(chat_id="123")
        assert backend._token == "env-token"

    def test_missing_token_raises(self, monkeypatch):
        monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
        from praisonai.bots._telegram_approval import TelegramApproval

        with pytest.raises(ValueError, match="[Tt]oken"):
            TelegramApproval(chat_id="123")

    def test_default_timeout(self):
        from praisonai.bots._telegram_approval import TelegramApproval

        backend = TelegramApproval(token="t", chat_id="123")
        assert backend._timeout == 300

    def test_custom_poll_interval(self):
        from praisonai.bots._telegram_approval import TelegramApproval

        backend = TelegramApproval(token="t", chat_id="123", poll_interval=1.0)
        assert backend._poll_interval == 1.0

    def test_repr_masks_token(self):
        from praisonai.bots._telegram_approval import TelegramApproval

        backend = TelegramApproval(token="1234567890:ABCDEF", chat_id="99")
        r = repr(backend)
        assert "1234567890:ABCDEF" not in r
        assert "99" in r


# ── Message Builder ─────────────────────────────────────────────────────────


class TestMessageBuilder:
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

    def test_message_contains_tool_name(self):
        from praisonai.bots._telegram_approval import TelegramApproval

        backend = TelegramApproval(token="t", chat_id="123")
        request = self._make_request(tool_name="delete_file")
        text = backend._build_message_text(request)
        assert "delete_file" in text

    def test_message_contains_risk_level(self):
        from praisonai.bots._telegram_approval import TelegramApproval

        backend = TelegramApproval(token="t", chat_id="123")
        request = self._make_request(risk_level="high")
        text = backend._build_message_text(request)
        assert "HIGH" in text

    def test_inline_keyboard_has_approve_deny(self):
        from praisonai.bots._telegram_approval import TelegramApproval

        backend = TelegramApproval(token="t", chat_id="123")
        request = self._make_request()
        kb = backend._build_inline_keyboard(request)
        kb_json = json.dumps(kb)
        assert "approve" in kb_json
        assert "deny" in kb_json

    def test_message_contains_agent_name(self):
        from praisonai.bots._telegram_approval import TelegramApproval

        backend = TelegramApproval(token="t", chat_id="123")
        request = self._make_request(agent_name="my-bot")
        text = backend._build_message_text(request)
        assert "my-bot" in text


# ── Async Approval Flow ────────────────────────────────────────────────────


class TestApprovalFlowAsync:
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

    def test_approved_via_callback(self):
        from praisonai.bots._telegram_approval import TelegramApproval

        backend = TelegramApproval(token="t", chat_id="123", timeout=5, poll_interval=0.1)
        poll_count = {"n": 0}

        async def mock_api(method, payload, **kwargs):
            if method == "sendMessage":
                return {"ok": True, "result": {"message_id": 42}}
            if method == "getUpdates":
                poll_count["n"] += 1
                if poll_count["n"] <= 1:
                    return {"ok": True, "result": []}
                return {
                    "ok": True,
                    "result": [{
                        "update_id": 100,
                        "callback_query": {
                            "id": "cb1",
                            "data": "approve",
                            "from": {"id": 999, "username": "tester"},
                            "message": {"message_id": 42},
                        },
                    }],
                }
            if method == "answerCallbackQuery":
                return {"ok": True}
            if method == "editMessageText":
                return {"ok": True}
            return {"ok": True}

        backend._telegram_api = mock_api
        decision = asyncio.run(backend.request_approval(self._make_request()))
        assert decision.approved is True
        assert decision.approver == "999"

    def test_denied_via_callback(self):
        from praisonai.bots._telegram_approval import TelegramApproval

        backend = TelegramApproval(token="t", chat_id="123", timeout=5, poll_interval=0.1)

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
                            "data": "deny",
                            "from": {"id": 999, "username": "tester"},
                            "message": {"message_id": 42},
                        },
                    }],
                }
            if method == "answerCallbackQuery":
                return {"ok": True}
            if method == "editMessageText":
                return {"ok": True}
            return {"ok": True}

        backend._telegram_api = mock_api
        decision = asyncio.run(backend.request_approval(self._make_request()))
        assert decision.approved is False

    def test_timeout_returns_denial(self):
        from praisonai.bots._telegram_approval import TelegramApproval

        backend = TelegramApproval(token="t", chat_id="123", timeout=0.5, poll_interval=0.1)

        async def mock_api(method, payload, **kwargs):
            if method == "sendMessage":
                return {"ok": True, "result": {"message_id": 42}}
            if method == "getUpdates":
                return {"ok": True, "result": []}
            if method == "editMessageText":
                return {"ok": True}
            return {"ok": True}

        backend._telegram_api = mock_api
        decision = asyncio.run(backend.request_approval(self._make_request()))
        assert decision.approved is False
        assert "timeout" in decision.reason.lower() or "timed out" in decision.reason.lower()

    def test_post_failure_returns_denial(self):
        from praisonai.bots._telegram_approval import TelegramApproval

        backend = TelegramApproval(token="t", chat_id="123", timeout=5, poll_interval=0.1)

        async def mock_api(method, payload, **kwargs):
            if method == "sendMessage":
                return {"ok": False, "description": "chat not found"}
            return {"ok": True}

        backend._telegram_api = mock_api
        decision = asyncio.run(backend.request_approval(self._make_request()))
        assert decision.approved is False
        assert "chat not found" in decision.reason

    def test_no_chat_id_returns_denial(self):
        from praisonai.bots._telegram_approval import TelegramApproval

        backend = TelegramApproval(token="t", chat_id="", timeout=2, poll_interval=0.1)
        decision = asyncio.run(backend.request_approval(self._make_request()))
        assert decision.approved is False
        assert "chat_id" in decision.reason.lower()

    def test_message_updated_after_approval(self):
        from praisonai.bots._telegram_approval import TelegramApproval

        backend = TelegramApproval(token="t", chat_id="123", timeout=5, poll_interval=0.1)
        update_calls = []

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
                            "from": {"id": 999, "username": "tester"},
                            "message": {"message_id": 42},
                        },
                    }],
                }
            if method == "answerCallbackQuery":
                return {"ok": True}
            if method == "editMessageText":
                update_calls.append(payload)
                return {"ok": True}
            return {"ok": True}

        backend._telegram_api = mock_api
        asyncio.run(backend.request_approval(self._make_request()))
        assert len(update_calls) == 1
        assert update_calls[0]["message_id"] == 42

    def test_ignores_unrelated_callback(self):
        """Callback for a different message_id is ignored."""
        from praisonai.bots._telegram_approval import TelegramApproval

        backend = TelegramApproval(token="t", chat_id="123", timeout=1, poll_interval=0.1)
        poll_count = {"n": 0}

        async def mock_api(method, payload, **kwargs):
            if method == "sendMessage":
                return {"ok": True, "result": {"message_id": 42}}
            if method == "getUpdates":
                poll_count["n"] += 1
                if poll_count["n"] <= 2:
                    return {
                        "ok": True,
                        "result": [{
                            "update_id": 100 + poll_count["n"],
                            "callback_query": {
                                "id": "cb1",
                                "data": "approve",
                                "from": {"id": 999},
                                "message": {"message_id": 99},  # different message
                            },
                        }],
                    }
                return {
                    "ok": True,
                    "result": [{
                        "update_id": 200,
                        "callback_query": {
                            "id": "cb2",
                            "data": "approve",
                            "from": {"id": 999, "username": "tester"},
                            "message": {"message_id": 42},
                        },
                    }],
                }
            if method == "answerCallbackQuery":
                return {"ok": True}
            if method == "editMessageText":
                return {"ok": True}
            return {"ok": True}

        backend._telegram_api = mock_api
        decision = asyncio.run(backend.request_approval(self._make_request()))
        assert decision.approved is True


# ── Agent Integration ───────────────────────────────────────────────────────


class TestAgentIntegration:
    def test_agent_accepts_telegram_approval(self):
        from praisonaiagents import Agent
        from praisonai.bots._telegram_approval import TelegramApproval

        backend = TelegramApproval(token="t", chat_id="123")
        agent = Agent(name="test", instructions="test", approval=backend)
        assert agent._approval_backend is backend


# ── Export / Import ─────────────────────────────────────────────────────────


class TestExports:
    def test_import_from_bots_package(self):
        from praisonai.bots import TelegramApproval
        assert TelegramApproval is not None

    def test_import_directly(self):
        from praisonai.bots._telegram_approval import TelegramApproval
        assert TelegramApproval is not None
