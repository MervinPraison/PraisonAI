"""Client transport-security guard (Issue #6307)."""

import logging

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
    "ws://127.1:8765",  # short-form loopback
    "ws://3232235786:8765",  # 192.168.1.10 as an integer
])
def test_allowed(url, monkeypatch, caplog):
    monkeypatch.delenv("PRAISONAI_ALLOW_INSECURE_WS", raising=False)
    with caplog.at_level(logging.WARNING):
        assert_secure_gateway_transport(url)
    assert "Plaintext gateway" not in caplog.text


@pytest.mark.parametrize("url", [
    "ws://gateway.example.com:8765",
    "http://gateway.example.com",
    "ws://gw.default.svc.cluster.local:8765",  # Kubernetes service DNS
    "ws://my-gw.tail1234.ts.net:8765",  # Tailscale MagicDNS
    "ws://gateway.internal:8765",
])
def test_plaintext_dns_name_warns_not_raises(url, monkeypatch, caplog):
    monkeypatch.delenv("PRAISONAI_ALLOW_INSECURE_WS", raising=False)
    with caplog.at_level(logging.WARNING):
        assert_secure_gateway_transport(url)
    assert "Plaintext gateway" in caplog.text


@pytest.mark.parametrize("url", [
    "ws://8.8.8.8:8765",
    "http://8.8.8.8",
    "ws://[2001:4860:4860::8888]:8765",
    # Alternate numeric spellings of public 8.8.8.8 must not pass as
    # single-label hostnames.
    "ws://134744072:8765",
    "ws://0x08080808:8765",
    "ws://0x8.0x8.0x8.0x8:8765",
])
def test_public_plaintext_refused(url, monkeypatch):
    monkeypatch.delenv("PRAISONAI_ALLOW_INSECURE_WS", raising=False)
    with pytest.raises(InsecureGatewayTransportError, match="wss://"):
        assert_secure_gateway_transport(url)


def test_break_glass(monkeypatch):
    monkeypatch.delenv("PRAISONAI_ALLOW_INSECURE_WS", raising=False)
    with pytest.raises(InsecureGatewayTransportError):
        assert_secure_gateway_transport("ws://8.8.8.8")
    monkeypatch.setenv("PRAISONAI_ALLOW_INSECURE_WS", "1")
    assert_secure_gateway_transport("ws://8.8.8.8")


def test_client_refuses_public_plaintext(monkeypatch):
    pytest.importorskip("websockets")
    from praisonai_bot.gateway.client import GatewayClient

    monkeypatch.delenv("PRAISONAI_ALLOW_INSECURE_WS", raising=False)
    with pytest.raises(InsecureGatewayTransportError):
        GatewayClient(url="ws://8.8.8.8:8765", agent_id="a")
    # Private DNS names (e.g. Kubernetes) keep working.
    GatewayClient(url="ws://gw.default.svc.cluster.local:8765", agent_id="a")


@pytest.mark.asyncio
async def test_client_sends_bearer_header_and_legacy_query_token(monkeypatch):
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

    # Query param kept for gateways released before Bearer support.
    assert seen["url"] == "ws://localhost:8765?token=s3cret"
    assert seen["kwargs"][client_mod._HEADERS_KWARG] == {"Authorization": "Bearer s3cret"}
