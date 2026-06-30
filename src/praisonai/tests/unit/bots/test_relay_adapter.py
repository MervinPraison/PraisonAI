"""Issue #2485 — out-of-process relay adapter inbound routing.

Verifies that a relay-backed bot routes connector-delivered inbound messages
through the configured agent (via a real ``BotSessionManager``) and relays the
reply back down the transport, rather than only firing manual ``on_message``
handlers. Also covers admission-gate splice point and dormant forwarding.
"""

from __future__ import annotations

import asyncio
from typing import List, Tuple

from praisonai.bots._relay_adapter import RelayAdapter
from praisonaiagents.gateway import (
    CapabilityDescriptor,
    DeliveryResult,
    GatewayMessage,
    TargetInfo,
)


class _FakeTransport:
    """Minimal RelayTransport that records sends and lets us inject inbound."""

    def __init__(self) -> None:
        self.handler = None
        self.sent: List[Tuple[TargetInfo, GatewayMessage]] = []
        self.dormant = False

    async def connect(self) -> CapabilityDescriptor:
        return CapabilityDescriptor(max_message_length=4096)

    def set_inbound_handler(self, handler) -> None:
        self.handler = handler

    async def send_outbound(self, target, message) -> DeliveryResult:
        self.sent.append((target, message))
        return DeliveryResult(ok=True, target=target.target)

    async def go_dormant(self) -> None:
        self.dormant = True

    async def disconnect(self) -> None:
        return None


class _EchoAgent:
    """Stand-in agent whose ``chat`` echoes the prompt."""

    def __init__(self) -> None:
        self.chat_history: List[dict] = []
        self.seen: List[str] = []

    def chat(self, prompt, *args, **kwargs):
        self.seen.append(prompt)
        return f"echo: {prompt}"


def test_inbound_message_routed_to_agent_and_reply_relayed():
    transport = _FakeTransport()
    agent = _EchoAgent()
    adapter = RelayAdapter(transport=transport, platform="telegram", agent=agent)

    async def scenario():
        await adapter.start()
        # The connector relays a normalised inbound message in.
        await transport.handler(
            GatewayMessage(content="hello", sender_id="u1", session_id="chan1")
        )

    asyncio.run(scenario())

    # Agent actually ran on the inbound prompt.
    assert agent.seen == ["hello"]
    # Reply was relayed back down the transport to the originating channel.
    assert len(transport.sent) == 1
    target, msg = transport.sent[0]
    assert target.target == "chan1"
    assert "echo: hello" in str(msg.content)


def test_manual_handlers_still_fire():
    transport = _FakeTransport()
    adapter = RelayAdapter(transport=transport, platform="telegram", agent=None)
    received = []
    adapter.on_message(lambda m: received.append(m))

    async def scenario():
        await adapter.start()
        await transport.handler(
            GatewayMessage(content="hi", sender_id="u1", session_id="c1")
        )

    asyncio.run(scenario())
    assert len(received) == 1
    # No agent → nothing relayed out.
    assert transport.sent == []


def test_session_built_for_admission_splice():
    """BotOS splices the admission gate onto ``adapter._session``; ensure it exists."""
    transport = _FakeTransport()
    adapter = RelayAdapter(transport=transport, platform="telegram", agent=_EchoAgent())

    async def scenario():
        await adapter.start()

    asyncio.run(scenario())
    assert adapter._session is not None
    assert hasattr(adapter._session, "_admission_gate")


def test_go_dormant_forwards_to_transport():
    transport = _FakeTransport()
    adapter = RelayAdapter(transport=transport, platform="telegram", agent=None)

    async def scenario():
        await adapter.start()
        await adapter.go_dormant()

    asyncio.run(scenario())
    assert transport.dormant is True
