#!/usr/bin/env python3
"""Regression tests for the server→client interactive request channel (Issue #5351).

The gateway can deliver a blocked HITL turn's approval / choice / input request
to a connected client and correlate the client's ``server_reply`` back into the
waiting turn — surviving the reconnects browser/mobile clients do constantly.

These tests pin:

- Core shapes: ``GatewayServerRequest`` / ``GatewayServerReply`` ``as_dict``.
- Channel end-to-end: ``request()`` delivers a ``server_request`` frame, tracks
  the open request, resolves on ``server_reply``, clears when answered, and
  returns ``None`` (clearing the open set) on timeout.
- Reconnect replay: only still-open requests are re-issued on join.
- Security: a reply is rejected unless the client owns the request's session
  (no cross-session hijack); an ``approval`` reply requires the APPROVALS scope,
  not merely WRITE; and the value must satisfy the request contract.
"""

import asyncio
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(REPO_ROOT / "src" / "praisonai"))
sys.path.insert(0, str(REPO_ROOT / "src" / "praisonai-agents"))

from praisonaiagents.gateway.protocols import (
    GatewayServerRequest,
    GatewayServerReply,
)
from praisonai_bot.gateway.server import WebSocketGateway, GatewaySession


# ---------------------------------------------------------------------------
# Core shapes
# ---------------------------------------------------------------------------

def test_server_request_as_dict_minimal():
    req = GatewayServerRequest(request_id="r1", kind="input", prompt="Name?")
    assert req.as_dict() == {"request_id": "r1", "kind": "input", "prompt": "Name?"}


def test_server_request_as_dict_choice_and_session():
    req = GatewayServerRequest(
        request_id="r2",
        kind="choice",
        prompt="Pick",
        options=["a", "b"],
        session_id="sess-1",
    )
    assert req.as_dict() == {
        "request_id": "r2",
        "kind": "choice",
        "prompt": "Pick",
        "options": ["a", "b"],
        "session_id": "sess-1",
    }


def test_server_reply_as_dict():
    assert GatewayServerReply(request_id="r1", value="allow").as_dict() == {
        "request_id": "r1",
        "value": "allow",
    }


# ---------------------------------------------------------------------------
# Test harness: a gateway with a connected, session-bound client that records
# every frame the server sends it.
# ---------------------------------------------------------------------------

def _connect(gw, client_id, session_id, scopes=None):
    """Register a fake connected client bound to a session; record sent frames."""
    sent: list = []

    async def _fake_send(cid, payload):
        if cid == client_id:
            sent.append(payload)

    gw._send_to_client = _fake_send  # type: ignore[assignment]
    gw._clients[client_id] = object()
    gw._client_sessions[client_id] = session_id
    if scopes is not None:
        gw._client_scopes[client_id] = list(scopes)
    session = GatewaySession(_session_id=session_id, _agent_id="agent-1")
    session._client_id = client_id
    gw._sessions[session_id] = session
    return sent


def test_request_delivers_frame_and_reply_resolves():
    async def go():
        gw = WebSocketGateway()
        sent = _connect(gw, "c1", "sess-1")
        req = GatewayServerRequest(
            request_id="req-1", kind="input", prompt="Name?", session_id="sess-1"
        )

        task = asyncio.create_task(gw.request_channel.request(req, timeout_s=5))
        await asyncio.sleep(0)  # let request() deliver + register

        # Frame delivered and request tracked as open.
        assert sent and sent[0]["type"] == "server_request"
        assert sent[0]["request"]["request_id"] == "req-1"
        assert gw.request_channel.open_requests("sess-1")[0].request_id == "req-1"

        # Client answers; the waiting turn is resolved with the reply.
        await gw._handle_client_message(
            "c1", {"type": "server_reply", "request_id": "req-1", "value": "Alice"}
        )
        reply = await asyncio.wait_for(task, timeout=1)
        assert reply is not None and reply.value == "Alice"
        # Answered request is cleared from the open set.
        assert gw.request_channel.open_requests("sess-1") == []

    asyncio.run(go())


def test_request_timeout_returns_none_and_clears():
    async def go():
        gw = WebSocketGateway()
        _connect(gw, "c1", "sess-1")
        req = GatewayServerRequest(
            request_id="req-t", kind="input", prompt="?", session_id="sess-1"
        )
        result = await gw.request_channel.request(req, timeout_s=0.01)
        assert result is None
        assert gw.request_channel.open_requests("sess-1") == []

    asyncio.run(go())


def test_reconnect_replays_only_open_requests():
    async def go():
        gw = WebSocketGateway()
        sent = _connect(gw, "c1", "sess-1")
        req = GatewayServerRequest(
            request_id="req-r", kind="input", prompt="?", session_id="sess-1"
        )
        task = asyncio.create_task(gw.request_channel.request(req, timeout_s=5))
        await asyncio.sleep(0)
        sent.clear()

        # Simulate a reconnect replay for the session.
        await gw._replay_open_requests("c1", "sess-1")
        assert sent and sent[0]["type"] == "server_request"
        assert sent[0]["request"]["request_id"] == "req-r"

        # After the request is answered, replay re-issues nothing.
        await gw._handle_client_message(
            "c1", {"type": "server_reply", "request_id": "req-r", "value": "x"}
        )
        await asyncio.wait_for(task, timeout=1)
        sent.clear()
        await gw._replay_open_requests("c1", "sess-1")
        assert sent == []

    asyncio.run(go())


# ---------------------------------------------------------------------------
# Security: cross-session hijack, approval scope, value contract
# ---------------------------------------------------------------------------

def test_reply_rejected_for_foreign_session():
    async def go():
        gw = WebSocketGateway()
        # Victim session sess-1 has an open request.
        sent1 = _connect(gw, "c1", "sess-1")
        req = GatewayServerRequest(
            request_id="req-x", kind="input", prompt="?", session_id="sess-1"
        )
        task = asyncio.create_task(gw.request_channel.request(req, timeout_s=5))
        await asyncio.sleep(0)

        # Attacker is a WRITE client bound to a *different* session.
        sent2 = _connect(gw, "c2", "sess-2", scopes=["read", "write"])
        await gw._handle_client_message(
            "c2", {"type": "server_reply", "request_id": "req-x", "value": "Evil"}
        )
        # Attacker gets a session_mismatch error; the victim turn stays open.
        assert any(f.get("code") == "session_mismatch" for f in sent2)
        assert not task.done()
        assert gw.request_channel.open_requests("sess-1")[0].request_id == "req-x"
        task.cancel()

    asyncio.run(go())


def test_approval_reply_requires_approvals_scope():
    async def go():
        gw = WebSocketGateway()
        # WRITE (but not APPROVALS) client owns the session with an approval req.
        sent = _connect(gw, "c1", "sess-1", scopes=["read", "write"])
        req = GatewayServerRequest(
            request_id="req-a", kind="approval", prompt="Deploy?", session_id="sess-1"
        )
        task = asyncio.create_task(gw.request_channel.request(req, timeout_s=5))
        await asyncio.sleep(0)

        await gw._handle_client_message(
            "c1", {"type": "server_reply", "request_id": "req-a", "value": "allow"}
        )
        # Rejected for insufficient scope; the approval turn is not resolved.
        assert any(f.get("code") == "insufficient_scope" for f in sent)
        assert not task.done()

        # With the APPROVALS scope it resolves.
        gw._client_scopes["c1"] = ["read", "write", "approvals"]
        await gw._handle_client_message(
            "c1", {"type": "server_reply", "request_id": "req-a", "value": "allow"}
        )
        reply = await asyncio.wait_for(task, timeout=1)
        assert reply.value == "allow"

    asyncio.run(go())


def test_reply_value_must_satisfy_contract():
    async def go():
        gw = WebSocketGateway()
        # Approval only accepts allow/deny.
        sent = _connect(gw, "c1", "sess-1", scopes=["read", "write", "approvals"])
        req = GatewayServerRequest(
            request_id="req-v", kind="approval", prompt="?", session_id="sess-1"
        )
        task = asyncio.create_task(gw.request_channel.request(req, timeout_s=5))
        await asyncio.sleep(0)
        await gw._handle_client_message(
            "c1", {"type": "server_reply", "request_id": "req-v", "value": "maybe"}
        )
        assert any(f.get("code") == "invalid_value" for f in sent)
        assert not task.done()

        # A valid allow/deny resolves it.
        await gw._handle_client_message(
            "c1", {"type": "server_reply", "request_id": "req-v", "value": "deny"}
        )
        reply = await asyncio.wait_for(task, timeout=1)
        assert reply.value == "deny"

    asyncio.run(go())


def test_choice_reply_must_be_offered_option():
    async def go():
        gw = WebSocketGateway()
        sent = _connect(gw, "c1", "sess-1", scopes=["read", "write"])
        req = GatewayServerRequest(
            request_id="req-c",
            kind="choice",
            prompt="Pick",
            options=["a", "b"],
            session_id="sess-1",
        )
        task = asyncio.create_task(gw.request_channel.request(req, timeout_s=5))
        await asyncio.sleep(0)

        await gw._handle_client_message(
            "c1", {"type": "server_reply", "request_id": "req-c", "value": "z"}
        )
        assert any(f.get("code") == "invalid_value" for f in sent)
        assert not task.done()

        await gw._handle_client_message(
            "c1", {"type": "server_reply", "request_id": "req-c", "value": "b"}
        )
        reply = await asyncio.wait_for(task, timeout=1)
        assert reply.value == "b"

    asyncio.run(go())


def test_reply_to_unknown_request_is_safe_noop():
    async def go():
        gw = WebSocketGateway()
        sent = _connect(gw, "c1", "sess-1", scopes=["read", "write"])
        await gw._handle_client_message(
            "c1", {"type": "server_reply", "request_id": "nope", "value": "x"}
        )
        assert any(
            f.get("type") == "server_reply_ack" and f.get("status") == "unknown_request"
            for f in sent
        )

    asyncio.run(go())
