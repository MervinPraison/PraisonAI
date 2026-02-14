"""
TDD tests for WebhookApproval backend.

Tests the webhook-based approval backend that POSTs requests and polls
a status endpoint for decisions.
"""

from __future__ import annotations

import asyncio

import pytest


# ── Protocol Conformance ────────────────────────────────────────────────────


class TestWebhookApprovalProtocol:
    def test_conforms_to_approval_protocol(self):
        from praisonaiagents.approval.protocols import ApprovalProtocol
        from praisonai.bots._webhook_approval import WebhookApproval

        backend = WebhookApproval(webhook_url="https://example.com/approve")
        assert isinstance(backend, ApprovalProtocol)

    def test_has_request_approval_sync(self):
        from praisonai.bots._webhook_approval import WebhookApproval

        backend = WebhookApproval(webhook_url="https://example.com/approve")
        assert hasattr(backend, "request_approval_sync")

    def test_has_request_approval_async(self):
        from praisonai.bots._webhook_approval import WebhookApproval

        backend = WebhookApproval(webhook_url="https://example.com/approve")
        assert asyncio.iscoroutinefunction(backend.request_approval)


# ── Construction & Config ───────────────────────────────────────────────────


class TestWebhookApprovalInit:
    def test_explicit_url(self):
        from praisonai.bots._webhook_approval import WebhookApproval

        backend = WebhookApproval(webhook_url="https://example.com/approve")
        assert backend._webhook_url == "https://example.com/approve"

    def test_env_var_url(self, monkeypatch):
        monkeypatch.setenv("APPROVAL_WEBHOOK_URL", "https://env.example.com/hook")
        from praisonai.bots._webhook_approval import WebhookApproval

        backend = WebhookApproval()
        assert backend._webhook_url == "https://env.example.com/hook"

    def test_missing_url_raises(self, monkeypatch):
        monkeypatch.delenv("APPROVAL_WEBHOOK_URL", raising=False)
        from praisonai.bots._webhook_approval import WebhookApproval

        with pytest.raises(ValueError, match="[Ww]ebhook"):
            WebhookApproval()

    def test_custom_headers(self):
        from praisonai.bots._webhook_approval import WebhookApproval

        backend = WebhookApproval(
            webhook_url="https://example.com",
            headers={"Authorization": "Bearer xxx"},
        )
        assert backend._headers["Authorization"] == "Bearer xxx"

    def test_repr(self):
        from praisonai.bots._webhook_approval import WebhookApproval

        backend = WebhookApproval(webhook_url="https://example.com/approve")
        assert "example.com" in repr(backend)


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

    def test_immediate_approval(self):
        """Webhook returns approved immediately in POST response."""
        from praisonai.bots._webhook_approval import WebhookApproval

        backend = WebhookApproval(webhook_url="https://example.com", timeout=5, poll_interval=0.1)

        async def mock_http(method, url, payload=None, **kwargs):
            if method == "POST":
                return {"approved": True, "reason": "Auto-approved by policy"}
            return {"status": "pending"}

        backend._http_request = mock_http
        decision = asyncio.run(backend.request_approval(self._make_request()))
        assert decision.approved is True
        assert "policy" in decision.reason.lower()

    def test_immediate_denial(self):
        from praisonai.bots._webhook_approval import WebhookApproval

        backend = WebhookApproval(webhook_url="https://example.com", timeout=5, poll_interval=0.1)

        async def mock_http(method, url, payload=None, **kwargs):
            if method == "POST":
                return {"approved": False, "reason": "Blocked by policy"}
            return {"status": "pending"}

        backend._http_request = mock_http
        decision = asyncio.run(backend.request_approval(self._make_request()))
        assert decision.approved is False

    def test_poll_approved(self):
        """POST returns no decision, poll finds approval."""
        from praisonai.bots._webhook_approval import WebhookApproval

        backend = WebhookApproval(webhook_url="https://example.com", timeout=5, poll_interval=0.1)
        poll_count = {"n": 0}

        async def mock_http(method, url, payload=None, **kwargs):
            if method == "POST":
                return {"status": "pending", "request_id": "abc"}
            if method == "GET":
                poll_count["n"] += 1
                if poll_count["n"] <= 1:
                    return {"status": "pending"}
                return {"approved": True, "reason": "Manager approved", "approver": "admin@co.com"}
            return {}

        backend._http_request = mock_http
        decision = asyncio.run(backend.request_approval(self._make_request()))
        assert decision.approved is True
        assert decision.approver == "admin@co.com"

    def test_poll_denied_via_status(self):
        from praisonai.bots._webhook_approval import WebhookApproval

        backend = WebhookApproval(webhook_url="https://example.com", timeout=5, poll_interval=0.1)

        async def mock_http(method, url, payload=None, **kwargs):
            if method == "POST":
                return {"status": "pending"}
            if method == "GET":
                return {"status": "denied", "reason": "Too risky"}
            return {}

        backend._http_request = mock_http
        decision = asyncio.run(backend.request_approval(self._make_request()))
        assert decision.approved is False

    def test_timeout(self):
        from praisonai.bots._webhook_approval import WebhookApproval

        backend = WebhookApproval(webhook_url="https://example.com", timeout=0.5, poll_interval=0.1)

        async def mock_http(method, url, payload=None, **kwargs):
            if method == "POST":
                return {"status": "pending"}
            if method == "GET":
                return {"status": "pending"}
            return {}

        backend._http_request = mock_http
        decision = asyncio.run(backend.request_approval(self._make_request()))
        assert decision.approved is False
        assert "timeout" in decision.reason.lower() or "timed out" in decision.reason.lower()

    def test_custom_status_url_template(self):
        from praisonai.bots._webhook_approval import WebhookApproval

        backend = WebhookApproval(
            webhook_url="https://example.com/hook",
            status_url="https://example.com/status/{request_id}",
            timeout=5,
            poll_interval=0.1,
        )
        polled_urls = []

        async def mock_http(method, url, payload=None, **kwargs):
            if method == "POST":
                return {"status": "pending"}
            if method == "GET":
                polled_urls.append(url)
                return {"approved": True, "reason": "ok"}
            return {}

        backend._http_request = mock_http
        asyncio.run(backend.request_approval(self._make_request()))
        assert len(polled_urls) >= 1
        assert "status/" in polled_urls[0]
        assert "{request_id}" not in polled_urls[0]

    def test_post_payload_includes_tool_info(self):
        from praisonai.bots._webhook_approval import WebhookApproval

        backend = WebhookApproval(webhook_url="https://example.com", timeout=5, poll_interval=0.1)
        posted_payloads = []

        async def mock_http(method, url, payload=None, **kwargs):
            if method == "POST":
                posted_payloads.append(payload)
                return {"approved": True}
            return {}

        backend._http_request = mock_http
        asyncio.run(backend.request_approval(self._make_request(tool_name="rm_file")))
        assert len(posted_payloads) == 1
        assert posted_payloads[0]["tool_name"] == "rm_file"
        assert "request_id" in posted_payloads[0]


# ── Export / Import ─────────────────────────────────────────────────────────


class TestExports:
    def test_import_from_bots_package(self):
        from praisonai.bots import WebhookApproval
        assert WebhookApproval is not None

    def test_import_directly(self):
        from praisonai.bots._webhook_approval import WebhookApproval
        assert WebhookApproval is not None
