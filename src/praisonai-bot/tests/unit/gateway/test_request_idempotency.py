#!/usr/bin/env python3
"""Request-idempotency for the operator control-frame path (Issue #5193).

The client->Gateway ``message`` control frame used to carry no request id and
the server did no request dedup, forcing at-most-once (lose an in-flight
request on a drop) or duplicate-the-turn (resend double-runs). These tests pin
the exactly-once contract:

- Server: a ``message`` frame with a ``request_id`` runs the turn once; a
  resend of the same id is deduped (acked ``duplicate``, not re-run).
- Server: an id-less frame keeps the legacy fire-and-forget behaviour (no
  dedup) — back-compat.
- Server: a request whose turn never ran (agent unavailable) releases the
  reservation so a later retry is not deduped away.
- Client: ``send`` attaches a stable ``request_id`` and, when ``queue=True``,
  queues while disconnected and flushes on reconnect with the SAME id.
- Protocol: ``MessageParams`` decodes the optional ``request_id`` field.
"""

import asyncio
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(REPO_ROOT / "src" / "praisonai"))
sys.path.insert(0, str(REPO_ROOT / "src" / "praisonai-agents"))
sys.path.insert(0, str(REPO_ROOT / "src" / "praisonai-bot"))

from praisonaiagents.gateway.protocols import MessageParams
from praisonai_bot.gateway.server import WebSocketGateway


# ---------------------------------------------------------------------------
# Protocol: optional request_id on the message frame
# ---------------------------------------------------------------------------

def test_message_params_decodes_request_id():
    m = MessageParams.from_frame(
        {"type": "message", "content": "hi", "request_id": "r-1"}
    )
    assert m.request_id == "r-1"


def test_message_params_request_id_optional():
    m = MessageParams.from_frame({"type": "message", "content": "hi"})
    assert m.request_id is None


# ---------------------------------------------------------------------------
# Server: exactly-once dedup on the message dispatch
# ---------------------------------------------------------------------------

def _make_gateway_with_session():
    gw = WebSocketGateway()
    calls = []

    async def _fake_process(session, message):
        calls.append(message.content)
        return "Started processing."

    gw._process_agent_message = _fake_process  # type: ignore[assignment]

    sent = []

    async def _fake_send(client_id, payload):
        sent.append(payload)

    gw._send_to_client = _fake_send  # type: ignore[assignment]

    session = gw.create_session("agent-1", client_id="client-1")
    gw._client_sessions["client-1"] = session.session_id
    # Register an agent so the turn is not short-circuited as unavailable.
    gw._agents[session.agent_id] = object()
    return gw, session, calls, sent


def test_duplicate_request_id_is_deduped():
    async def go():
        gw, session, calls, sent = _make_gateway_with_session()
        frame = {"type": "message", "content": "run once", "request_id": "rid-1"}

        await gw._handle_client_message("client-1", dict(frame))
        await gw._handle_client_message("client-1", dict(frame))

        # The turn ran exactly once despite two identical frames.
        assert calls == ["run once"]
        # The second frame was acked as a duplicate.
        statuses = [p.get("status") for p in sent if p.get("type") == "response"]
        assert "accepted" in statuses
        assert "duplicate" in statuses

    asyncio.run(go())


def test_missing_request_id_keeps_legacy_no_dedup():
    async def go():
        gw, session, calls, sent = _make_gateway_with_session()
        frame = {"type": "message", "content": "run"}

        await gw._handle_client_message("client-1", dict(frame))
        await gw._handle_client_message("client-1", dict(frame))

        # No id -> no dedup -> the turn runs each time (back-compat).
        assert calls == ["run", "run"]

    asyncio.run(go())


def test_distinct_request_ids_both_run():
    async def go():
        gw, session, calls, sent = _make_gateway_with_session()
        await gw._handle_client_message(
            "client-1", {"type": "message", "content": "a", "request_id": "r-a"}
        )
        await gw._handle_client_message(
            "client-1", {"type": "message", "content": "b", "request_id": "r-b"}
        )
        assert calls == ["a", "b"]

    asyncio.run(go())


def test_unavailable_agent_releases_reservation_for_retry():
    async def go():
        gw, session, calls, sent = _make_gateway_with_session()
        # Drop the agent so the turn cannot run.
        gw._agents.pop(session.agent_id, None)

        await gw._handle_client_message(
            "client-1", {"type": "message", "content": "x", "request_id": "rid-2"}
        )
        # Turn never ran; the reservation was released, so a retry (once the
        # agent is back) is NOT deduped away.
        gw._agents[session.agent_id] = object()
        await gw._handle_client_message(
            "client-1", {"type": "message", "content": "x", "request_id": "rid-2"}
        )
        assert calls == ["x"]

    asyncio.run(go())


def test_failed_turn_releases_reservation_for_retry():
    async def go():
        gw, session, calls, sent = _make_gateway_with_session()

        # First delivery: _process_agent_message raises before the turn is
        # committed (e.g. a socket failure during a preliminary status send).
        async def _boom(session, message):
            calls.append(message.content)
            raise RuntimeError("preliminary send failed")

        gw._process_agent_message = _boom  # type: ignore[assignment]

        raised = False
        try:
            await gw._handle_client_message(
                "client-1", {"type": "message", "content": "x", "request_id": "rid-3"}
            )
        except RuntimeError:
            raised = True
        assert raised

        # The reservation was released, so a legitimate retry of the SAME id is
        # not deduped away as a phantom duplicate — the turn gets a real chance.
        async def _ok(session, message):
            calls.append(message.content)
            return "Started processing."

        gw._process_agent_message = _ok  # type: ignore[assignment]
        await gw._handle_client_message(
            "client-1", {"type": "message", "content": "x", "request_id": "rid-3"}
        )
        assert calls == ["x", "x"]

    asyncio.run(go())


# ---------------------------------------------------------------------------
# Client: safe queue-and-flush with a stable request_id
# ---------------------------------------------------------------------------

def _make_client():
    from praisonai_bot.gateway.client import GatewayClient

    client = GatewayClient(url="ws://x", agent_id="a")
    return client


def test_send_queues_while_disconnected():
    async def go():
        client = _make_client()
        # Not connected: a queued send is stored, not raised.
        rid = await client.send("hello", queue=True)
        assert rid is not None
        assert len(client._pending_outbox) == 1
        frame = client._pending_outbox[0]
        assert frame["type"] == "message"
        assert frame["content"] == "hello"
        assert frame["request_id"] == rid

    asyncio.run(go())


def test_send_raises_when_not_queued():
    async def go():
        client = _make_client()
        raised = False
        try:
            await client.send("hello")
        except ConnectionError:
            raised = True
        assert raised
        assert client._pending_outbox == []

    asyncio.run(go())


def test_flush_outbox_resends_same_request_id():
    async def go():
        client = _make_client()
        sent = []

        async def _fake_send_frame(frame):
            sent.append(frame)

        client._send_frame = _fake_send_frame  # type: ignore[assignment]

        rid = await client.send("queued", queue=True)
        await client._flush_outbox()

        assert len(sent) == 1
        assert sent[0]["request_id"] == rid
        assert sent[0]["content"] == "queued"
        # Outbox is drained after a successful flush.
        assert client._pending_outbox == []

    asyncio.run(go())


def test_flush_requeues_on_failure():
    async def go():
        client = _make_client()

        async def _boom(frame):
            raise RuntimeError("socket died")

        client._send_frame = _boom  # type: ignore[assignment]

        await client.send("q1", queue=True)
        await client._flush_outbox()
        # The frame that failed to send is retained for the next reconnect.
        assert len(client._pending_outbox) == 1

    asyncio.run(go())


def test_stable_request_id_is_preserved_across_queue():
    async def go():
        client = _make_client()
        rid = await client.send("m", request_id="fixed-id", queue=True)
        assert rid == "fixed-id"
        assert client._pending_outbox[0]["request_id"] == "fixed-id"

    asyncio.run(go())
