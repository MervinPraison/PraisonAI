"""Webhook receivers bind through the shared bind guard.

The signing secret is the token: a keyless receiver may only bind loopback.
An unresolved ``${VAR}`` placeholder is not a secret (its text is public).
"""

import asyncio
import hashlib
import hmac

import pytest

pytest.importorskip("aiohttp")

from praisonai_bot.bots.webhook_security import configured_secret, verify_hmac

SECRET_ENVS = (
    "WHATSAPP_APP_SECRET", "LINEAR_WEBHOOK_SECRET", "AGENTMAIL_WEBHOOK_SECRET",
    "PRAISONAI_WEBHOOK_HOST", "PRAISONAI_INSECURE_WEBHOOKS",
)


class _Bound(Exception):
    """Raised by the fake TCPSite.start so the receiver never serves."""


@pytest.fixture
def sites(monkeypatch):
    for var in SECRET_ENVS:
        monkeypatch.delenv(var, raising=False)
    from aiohttp import web

    hosts = []

    class FakeSite:
        def __init__(self, runner, host, port, **kw):
            hosts.append(host)

        async def start(self):
            raise _Bound()

    monkeypatch.setattr(web, "TCPSite", FakeSite)
    return hosts


def _whatsapp(secret=""):
    from praisonai_bot.bots.whatsapp import WhatsAppBot

    bot = WhatsAppBot(token="t", phone_number_id="1", app_secret=secret)
    return bot._start_cloud_mode()


def _linear(secret=""):
    from praisonai_bot.bots.linear import LinearBot

    return LinearBot(token="t", signing_secret=secret).start()


def _agentmail(secret="", monkeypatch=None):
    from praisonai_bot.bots.agentmail import AgentMailBot

    if secret:
        monkeypatch.setenv("AGENTMAIL_WEBHOOK_SECRET", secret)
    return AgentMailBot(token="t")._start_webhook_mode()


def _webhook(secret=""):
    from praisonai_bot.bots.webhook import WebhookBot

    verify = {"hmac": {"header": "X-Sig", "secret": secret}} if secret else None
    return WebhookBot(webhook_port=8099, verify=verify).start()


RECEIVERS = {
    "whatsapp": lambda s, mp: _whatsapp(s),
    "linear": lambda s, mp: _linear(s),
    "agentmail": lambda s, mp: _agentmail(s, mp),
    "webhook": lambda s, mp: _webhook(s),
}


@pytest.mark.parametrize("name", sorted(RECEIVERS))
def test_keyless_public_bind_refuses(name, sites, monkeypatch):
    with pytest.raises(ValueError, match="refuses to bind non-loopback"):
        asyncio.run(RECEIVERS[name]("", monkeypatch))
    assert sites == []


@pytest.mark.parametrize("name", sorted(RECEIVERS))
def test_unresolved_placeholder_secret_counts_as_keyless(name, sites, monkeypatch):
    with pytest.raises(ValueError, match="refuses to bind non-loopback"):
        asyncio.run(RECEIVERS[name]("${UNSET_SECRET}", monkeypatch))
    assert sites == []


@pytest.mark.parametrize("name", sorted(RECEIVERS))
def test_keyless_loopback_bind_starts(name, sites, monkeypatch):
    monkeypatch.setenv("PRAISONAI_WEBHOOK_HOST", "127.0.0.1")
    with pytest.raises(_Bound):
        asyncio.run(RECEIVERS[name]("", monkeypatch))
    assert sites == ["127.0.0.1"]


@pytest.mark.parametrize("name", sorted(RECEIVERS))
def test_public_bind_with_secret_starts(name, sites, monkeypatch):
    with pytest.raises(_Bound):
        asyncio.run(RECEIVERS[name]("s3cret", monkeypatch))
    assert sites == ["0.0.0.0"]


def test_configured_secret():
    assert configured_secret("abc") == "abc"
    assert configured_secret("${LINEAR_WEBHOOK_SECRET}") is None
    assert configured_secret(b"${X}") is None
    assert configured_secret("") is None and configured_secret(None) is None


def test_placeholder_key_never_verifies():
    """A signature made with the literal placeholder text must not verify."""
    body = b'{"x": 1}'
    key = "${LINEAR_WEBHOOK_SECRET}"
    sig = hmac.new(key.encode(), body, hashlib.sha256).hexdigest()
    assert verify_hmac(key, body, sig) is False
    real = hmac.new(b"real", body, hashlib.sha256).hexdigest()
    assert verify_hmac("real", body, real) is True
