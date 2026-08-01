"""Tests for the generic declarative webhook-trigger channel (Issue #3580).

Covers: registry wiring (``webhook`` is a first-class built-in loader), route
matching, prompt templating, declarative verifier construction, and the HTTP
handler dispatch/verification/silent-route paths — all without binding a real
socket.
"""

import hashlib
import hmac
import json
from unittest.mock import AsyncMock

import pytest

from praisonai_bot.bots import _registry as R
from praisonai_bot.bots.webhook import (
    WebhookBot,
    WebhookRoute,
    render_prompt,
    _build_verifier_from_config,
)


# ── Registry wiring ─────────────────────────────────────────────────


def test_webhook_is_builtin_platform():
    reg = R.BotPlatformRegistry()
    assert "webhook" in reg.list_names()
    assert reg.resolve("webhook").__name__ == "WebhookBot"


def test_webhook_default_capabilities_declare_webhooks():
    caps = WebhookBot.default_capabilities()
    assert caps.accepts_webhooks is True
    assert caps.verifies_webhook_signature is True


# ── Route matching ──────────────────────────────────────────────────


def _event():
    return {
        "payload": {"action": "opened", "issue": {"number": 7, "title": "Hi"}},
        "headers": {"X-GitHub-Event": "issues"},
        "query": {},
    }


def test_route_matches_declarative_filter():
    route = WebhookRoute(
        when={
            "all": [
                {"field": "headers.X-GitHub-Event", "equals": "issues"},
                {"field": "payload.action", "in": ["opened", "reopened"]},
            ]
        }
    )
    assert route.matches(_event())


def test_route_from_dict_and_silent():
    route = WebhookRoute.from_dict(
        {"when": {"field": "payload.action", "equals": "closed"}, "silent": True}
    )
    assert route.silent is True
    assert not route.matches(_event())


def test_catch_all_route_when_no_when():
    assert WebhookRoute().matches(_event())


# ── Prompt templating ───────────────────────────────────────────────


def test_render_prompt_fills_placeholders():
    out = render_prompt(
        "New issue #{{ payload.issue.number }}: {{ payload.issue.title }}", _event()
    )
    assert out == "New issue #7: Hi"


def test_render_prompt_missing_field_is_blank():
    assert render_prompt("x={{ payload.nope }}", _event()) == "x="


def test_render_prompt_none_uses_payload_json():
    out = render_prompt(None, _event())
    assert json.loads(out)["action"] == "opened"


# ── Declarative verifier construction ───────────────────────────────


def test_build_verifier_from_hmac_mapping():
    v = _build_verifier_from_config(
        {"hmac": {"header": "X-Sig", "secret": "s3cr3t", "prefix": "sha256="}}
    )
    assert v is not None
    body = b'{"a":1}'
    sig = "sha256=" + hmac.new(b"s3cr3t", body, hashlib.sha256).hexdigest()
    assert v.verify(headers={"X-Sig": sig}, raw_body=body)
    assert not v.verify(headers={"X-Sig": "sha256=deadbeef"}, raw_body=body)


def test_build_verifier_passthrough_object():
    class V:
        def verify(self, *, headers, raw_body):
            return True

    obj = V()
    assert _build_verifier_from_config(obj) is obj


def test_build_verifier_none():
    assert _build_verifier_from_config(None) is None


# ── HTTP handler behaviour ──────────────────────────────────────────


class _FakeRequest:
    def __init__(self, body: bytes, headers: dict, query: dict = None):
        self._body = body
        self.headers = headers
        self.query = query or {}

    async def read(self):
        return self._body


def _make_bot(monkeypatch, **kwargs):
    """Build a WebhookBot with a stubbed session manager (no real session I/O)."""
    bot = WebhookBot(agent=object(), **kwargs)
    bot._session_mgr = AsyncMock()
    return bot


@pytest.mark.asyncio
async def test_handler_dispatches_matching_route(monkeypatch):
    monkeypatch.setenv("PRAISONAI_INSECURE_WEBHOOKS", "true")
    bot = _make_bot(
        monkeypatch,
        routes=[
            WebhookRoute(
                when={"field": "payload.action", "equals": "opened"},
                prompt="issue {{ payload.issue.number }}",
            )
        ],
    )
    req = _FakeRequest(
        json.dumps(_event()["payload"]).encode(),
        {"X-GitHub-Event": "issues"},
    )
    resp = await bot._handle_webhook(req)
    assert resp.status == 200
    bot._session_mgr.chat.assert_awaited_once()
    # The rendered prompt reached the agent.
    _, kwargs = bot._session_mgr.chat.call_args
    args = bot._session_mgr.chat.call_args.args
    assert "issue 7" in args[2]


@pytest.mark.asyncio
async def test_handler_silent_route_acks_without_agent(monkeypatch):
    monkeypatch.setenv("PRAISONAI_INSECURE_WEBHOOKS", "true")
    bot = _make_bot(
        monkeypatch,
        routes=[
            WebhookRoute(
                when={"field": "payload.action", "equals": "opened"}, silent=True
            )
        ],
    )
    req = _FakeRequest(json.dumps(_event()["payload"]).encode(), {})
    resp = await bot._handle_webhook(req)
    assert resp.status == 200
    bot._session_mgr.chat.assert_not_awaited()


@pytest.mark.asyncio
async def test_handler_rejects_bad_signature(monkeypatch):
    monkeypatch.delenv("PRAISONAI_INSECURE_WEBHOOKS", raising=False)
    bot = _make_bot(
        monkeypatch,
        verify={"hmac": {"header": "X-Sig", "secret": "s3cr3t"}},
    )
    req = _FakeRequest(b'{"action":"opened"}', {"X-Sig": "sha256=bad"})
    resp = await bot._handle_webhook(req)
    assert resp.status == 401
    bot._session_mgr.chat.assert_not_awaited()


@pytest.mark.asyncio
async def test_handler_accepts_valid_signature(monkeypatch):
    monkeypatch.delenv("PRAISONAI_INSECURE_WEBHOOKS", raising=False)
    bot = _make_bot(
        monkeypatch,
        verify={"hmac": {"header": "X-Sig", "secret": "s3cr3t"}},
    )
    body = b'{"action":"opened"}'
    sig = hmac.new(b"s3cr3t", body, hashlib.sha256).hexdigest()
    req = _FakeRequest(body, {"X-Sig": sig})
    resp = await bot._handle_webhook(req)
    assert resp.status == 200
    bot._session_mgr.chat.assert_awaited_once()


@pytest.mark.asyncio
async def test_handler_no_matching_route_acks(monkeypatch):
    monkeypatch.setenv("PRAISONAI_INSECURE_WEBHOOKS", "true")
    bot = _make_bot(
        monkeypatch,
        routes=[WebhookRoute(when={"field": "payload.action", "equals": "closed"})],
    )
    req = _FakeRequest(json.dumps(_event()["payload"]).encode(), {})
    resp = await bot._handle_webhook(req)
    assert resp.status == 200
    bot._session_mgr.chat.assert_not_awaited()
