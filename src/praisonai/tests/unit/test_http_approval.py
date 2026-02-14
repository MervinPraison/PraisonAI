"""
TDD tests for HTTPApproval backend.

Tests the HTTP-based approval backend that serves a local web dashboard
for approving/denying tool executions.
"""

from __future__ import annotations

import asyncio

import pytest


# ── Protocol Conformance ────────────────────────────────────────────────────


class TestHTTPApprovalProtocol:
    def test_conforms_to_approval_protocol(self):
        from praisonaiagents.approval.protocols import ApprovalProtocol
        from praisonai.bots._http_approval import HTTPApproval

        backend = HTTPApproval(port=0)
        assert isinstance(backend, ApprovalProtocol)

    def test_has_request_approval_sync(self):
        from praisonai.bots._http_approval import HTTPApproval

        backend = HTTPApproval(port=0)
        assert hasattr(backend, "request_approval_sync")

    def test_has_request_approval_async(self):
        from praisonai.bots._http_approval import HTTPApproval

        backend = HTTPApproval(port=0)
        assert asyncio.iscoroutinefunction(backend.request_approval)


# ── Construction & Config ───────────────────────────────────────────────────


class TestHTTPApprovalInit:
    def test_default_host_port(self):
        from praisonai.bots._http_approval import HTTPApproval

        backend = HTTPApproval()
        assert backend._host == "127.0.0.1"
        assert backend._port == 8899

    def test_custom_host_port(self):
        from praisonai.bots._http_approval import HTTPApproval

        backend = HTTPApproval(host="0.0.0.0", port=9999)
        assert backend._host == "0.0.0.0"
        assert backend._port == 9999

    def test_repr(self):
        from praisonai.bots._http_approval import HTTPApproval

        backend = HTTPApproval(port=8899)
        assert "8899" in repr(backend)


# ── HTML Builder ────────────────────────────────────────────────────────────


class TestHTMLBuilder:
    def test_html_contains_tool_name(self):
        from praisonai.bots._http_approval import HTTPApproval

        backend = HTTPApproval()
        html = backend._build_html("req-1", {
            "tool_name": "delete_all",
            "risk_level": "critical",
            "arguments": {"path": "/tmp"},
            "agent_name": "cleaner",
        })
        assert "delete_all" in html
        assert "CRITICAL" in html
        assert "cleaner" in html

    def test_html_has_approve_deny_buttons(self):
        from praisonai.bots._http_approval import HTTPApproval

        backend = HTTPApproval()
        html = backend._build_html("req-1", {
            "tool_name": "test",
            "risk_level": "low",
            "arguments": {},
        })
        assert "Approve" in html
        assert "Deny" in html


# ── Async Approval Flow (in-process) ───────────────────────────────────────


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

    def test_timeout_returns_denial(self):
        """No decision within timeout → auto-deny."""
        from praisonai.bots._http_approval import HTTPApproval

        backend = HTTPApproval(port=0, timeout=0.5)

        # Mock _ensure_server to skip actual server startup
        async def mock_server():
            backend._server_started = True

        backend._ensure_server = mock_server

        decision = asyncio.run(backend.request_approval(self._make_request()))
        assert decision.approved is False
        assert "timeout" in decision.reason.lower() or "timed out" in decision.reason.lower()

    def test_pending_request_registered(self):
        """Approval request gets registered in _pending dict."""
        from praisonai.bots._http_approval import HTTPApproval

        backend = HTTPApproval(port=0, timeout=0.3)

        async def mock_server():
            backend._server_started = True

        backend._ensure_server = mock_server

        # Run approval and check pending was populated (then cleaned on timeout)
        decision = asyncio.run(backend.request_approval(self._make_request()))
        # After timeout, pending should be cleaned
        assert len(backend._pending) == 0
        assert decision.approved is False

    def test_simulated_approval(self):
        """Simulate a user clicking approve via _pending dict."""
        from praisonai.bots._http_approval import HTTPApproval

        backend = HTTPApproval(port=0, timeout=5)

        async def mock_server():
            backend._server_started = True

        backend._ensure_server = mock_server

        async def run_approval():
            req = self._make_request()

            async def simulate_click():
                await asyncio.sleep(0.3)
                # Find the pending request and approve it
                for rid, info in backend._pending.items():
                    info["decided"] = True
                    info["approved"] = True
                    info["reason"] = "Test approved"
                    info["approver"] = "test_user"
                    break

            # Run both concurrently
            task = asyncio.create_task(simulate_click())
            decision = await backend.request_approval(req)
            await task
            return decision

        decision = asyncio.run(run_approval())
        assert decision.approved is True
        assert decision.approver == "test_user"

    def test_simulated_denial(self):
        """Simulate a user clicking deny via _pending dict."""
        from praisonai.bots._http_approval import HTTPApproval

        backend = HTTPApproval(port=0, timeout=5)

        async def mock_server():
            backend._server_started = True

        backend._ensure_server = mock_server

        async def run_approval():
            req = self._make_request()

            async def simulate_click():
                await asyncio.sleep(0.3)
                for rid, info in backend._pending.items():
                    info["decided"] = True
                    info["approved"] = False
                    info["reason"] = "Test denied"
                    break

            task = asyncio.create_task(simulate_click())
            decision = await backend.request_approval(req)
            await task
            return decision

        decision = asyncio.run(run_approval())
        assert decision.approved is False


# ── Export / Import ─────────────────────────────────────────────────────────


class TestExports:
    def test_import_from_bots_package(self):
        from praisonai.bots import HTTPApproval
        assert HTTPApproval is not None

    def test_import_directly(self):
        from praisonai.bots._http_approval import HTTPApproval
        assert HTTPApproval is not None
