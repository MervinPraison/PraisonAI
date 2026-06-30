"""Unit tests for the out-of-process platform-connector relay (Issue #2485).

Covers the core ``CapabilityDescriptor`` dataclass and structural conformance
to the ``RelayTransport`` protocol.
"""

import asyncio

import pytest

from praisonaiagents.gateway import (
    CapabilityDescriptor,
    DeliveryResult,
    GatewayMessage,
    RelayTransport,
    TargetInfo,
)


def test_capability_descriptor_defaults():
    caps = CapabilityDescriptor(max_message_length=4096)
    assert caps.max_message_length == 4096
    assert caps.length_unit == "chars"
    assert caps.supports_edit is False
    assert caps.supports_draft_streaming is False
    assert caps.markdown_dialect == "none"


def test_capability_descriptor_is_frozen():
    caps = CapabilityDescriptor(max_message_length=10)
    with pytest.raises(Exception):
        caps.max_message_length = 20  # type: ignore[misc]


def test_capability_descriptor_roundtrip():
    caps = CapabilityDescriptor(
        max_message_length=4096,
        length_unit="utf16",
        supports_edit=True,
        supports_draft_streaming=True,
        markdown_dialect="markdownv2",
    )
    assert CapabilityDescriptor.from_dict(caps.as_dict()) == caps


def test_capability_descriptor_from_dict_uses_defaults():
    caps = CapabilityDescriptor.from_dict({"max_message_length": 2000})
    assert caps == CapabilityDescriptor(max_message_length=2000)


class _ConformingTransport:
    """Minimal object satisfying the RelayTransport protocol."""

    def __init__(self):
        self.handler = None

    async def connect(self):
        return CapabilityDescriptor(max_message_length=4096)

    def set_inbound_handler(self, handler):
        self.handler = handler

    async def send_outbound(self, target, message):
        return DeliveryResult(ok=True, target=target.target)

    async def go_dormant(self):
        return None

    async def disconnect(self):
        return None


def test_relay_transport_structural_conformance():
    assert isinstance(_ConformingTransport(), RelayTransport)


def test_relay_transport_missing_method_not_conforming():
    class Incomplete:
        async def connect(self):
            return CapabilityDescriptor(max_message_length=1)

    assert not isinstance(Incomplete(), RelayTransport)


def test_relay_transport_handshake_and_send():
    transport = _ConformingTransport()

    async def scenario():
        caps = await transport.connect()
        assert caps.max_message_length == 4096
        result = await transport.send_outbound(
            TargetInfo(target="chan1", platform="telegram"),
            GatewayMessage(content="hi", sender_id="gw", session_id="chan1"),
        )
        assert result.ok and result.target == "chan1"

    asyncio.run(scenario())
