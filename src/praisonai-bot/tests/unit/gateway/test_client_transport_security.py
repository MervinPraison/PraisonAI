"""Client transport-security guard (Issue #6307)."""

import pytest

from praisonaiagents.gateway import (
    InsecureGatewayTransportError,
    assert_secure_gateway_transport,
)


@pytest.mark.parametrize("url", [
    "ws://localhost:8765",
    "ws://127.0.0.1:8765",
    "ws://[::1]:8765",
    "ws://192.168.1.10:8765",
    "ws://10.0.0.5:8765",
    "ws://100.101.102.103:8765",  # Tailscale / CGNAT
    "ws://gateway:8765",  # docker-compose service name
    "wss://gateway.example.com:8765",
    "wss://203.0.113.7",
])
def test_allowed(url, monkeypatch):
    monkeypatch.delenv("PRAISONAI_ALLOW_INSECURE_WS", raising=False)
    assert_secure_gateway_transport(url)


@pytest.mark.parametrize("url", [
    "ws://gateway.example.com:8765",
    "ws://8.8.8.8:8765",
    "http://gateway.example.com",
])
def test_public_plaintext_refused(url, monkeypatch):
    monkeypatch.delenv("PRAISONAI_ALLOW_INSECURE_WS", raising=False)
    with pytest.raises(InsecureGatewayTransportError, match="wss://"):
        assert_secure_gateway_transport(url)


def test_break_glass(monkeypatch):
    monkeypatch.delenv("PRAISONAI_ALLOW_INSECURE_WS", raising=False)
    assert_secure_gateway_transport("ws://gateway.example.com", allow_insecure=True)
    monkeypatch.setenv("PRAISONAI_ALLOW_INSECURE_WS", "1")
    assert_secure_gateway_transport("ws://gateway.example.com")


def test_client_refuses_public_plaintext(monkeypatch):
    pytest.importorskip("websockets")
    from praisonai_bot.gateway.client import GatewayClient

    monkeypatch.delenv("PRAISONAI_ALLOW_INSECURE_WS", raising=False)
    with pytest.raises(InsecureGatewayTransportError):
        GatewayClient(url="ws://gateway.example.com:8765", agent_id="a")
    GatewayClient(url="ws://gateway.example.com:8765", agent_id="a", allow_insecure=True)


@pytest.mark.asyncio
async def test_client_sends_token_in_header_not_url(monkeypatch):
    pytest.importorskip("websockets")
    import praisonai_bot.gateway.client as client_mod

    seen = {}

    async def _fake_connect(url, **kwargs):
        seen["url"] = url
        seen["kwargs"] = kwargs
        raise ConnectionRefusedError("stop here")

    monkeypatch.setattr(client_mod.websockets, "connect", _fake_connect)
    client = client_mod.GatewayClient(url="ws://localhost:8765", agent_id="a", token="s3cret")
    with pytest.raises(ConnectionRefusedError):
        await client._connect_once()

    assert "s3cret" not in seen["url"]
    assert seen["kwargs"][client_mod._HEADERS_KWARG] == {"Authorization": "Bearer s3cret"}
