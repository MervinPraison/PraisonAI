"""A valid HMAC signature authenticates a ``/hooks/<path>`` delivery (#6034).

Signed providers (GitHub, Stripe, Slack) cannot send a bearer token, so on an
externally bound gateway (which always has an ``auth_token``) a hook with only
``secret`` must not fall back to gateway auth. The real ``hook_handler`` /
``_check_hook_auth`` / ``_check_auth`` closures are extracted from
``WebSocketGateway.start()`` so no web server is needed.
"""
import ast
import hashlib
import hmac
import inspect
import json
import textwrap

import pytest

import praisonai_bot.gateway.server as srv
from praisonaiagents.gateway import HookConfig

SECRET = "gh-webhook-secret"
GATEWAY_TOKEN = "gw-operator-token"


class _Resp:
    def __init__(self, content, status_code=200, headers=None):
        self.content, self.status_code = content, status_code


class _Req:
    def __init__(self, body, headers, query=None):
        self.path_params = {"path": "github"}
        self.headers = {k.lower(): v for k, v in headers.items()}
        self.query_params = query or {}
        self.client = type("C", (), {"host": "140.82.115.10"})()
        self._body = body

    async def body(self):
        return self._body


class _Gateway:
    def __init__(self, hook):
        self.config = type("Cfg", (), {
            "auth_token": GATEWAY_TOKEN, "bind_host": "0.0.0.0", "host": "0.0.0.0",
        })()
        self._hook = hook
        self._seen = set()
        self.runs = 0

    def get_hook(self, path):
        return self._hook if path == self._hook.path else None

    def _hook_reserve(self, key):
        if key in self._seen:
            return False
        self._seen.add(key)
        return True

    def _hook_release(self, key):
        self._seen.discard(key)

    def _hook_record(self, key):
        pass

    async def _run_hook(self, hook, payload):
        self.runs += 1
        return {"ok": True}


def _handler(gw, monkeypatch):
    monkeypatch.delenv("ALLOW_LOOPBACK_BYPASS", raising=False)
    src = textwrap.dedent(inspect.getsource(srv.WebSocketGateway.start))
    fn = ast.parse(src).body[0]
    wanted = {"_loopback_bypass_active", "_check_auth", "_check_hook_auth", "hook_handler"}
    nodes = [
        n for n in fn.body
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name in wanted
    ]
    assert {n.name for n in nodes} == wanted
    ns = dict(vars(srv))
    ns.update(self=gw, JSONResponse=_Resp)
    exec(compile(ast.Module(body=nodes, type_ignores=[]), srv.__file__, "exec"), ns)
    return ns["hook_handler"]


def _delivery(n, secret=SECRET):
    body = json.dumps({"action": "opened", "issue": {"number": n}}).encode()
    sig = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return body, {"X-Hub-Signature-256": sig, "X-GitHub-Event": "issues"}


def _hook(**kw):
    return HookConfig(path="github", agent="triage", idempotency_key="{issue.number}", **kw)


@pytest.mark.asyncio
async def test_signed_delivery_accepted_without_token(monkeypatch):
    gw = _Gateway(_hook(secret=SECRET))
    resp = await _handler(gw, monkeypatch)(_Req(*_delivery(1)))
    assert resp.status_code == 200
    assert gw.runs == 1


@pytest.mark.asyncio
async def test_bad_or_missing_signature_rejected(monkeypatch):
    gw = _Gateway(_hook(secret=SECRET))
    handler = _handler(gw, monkeypatch)
    body, headers = _delivery(2, secret="wrong")
    assert (await handler(_Req(body, headers))).status_code == 401
    assert (await handler(_Req(body, {}))).status_code == 401
    # A valid gateway token does not stand in for a bad signature.
    resp = await handler(_Req(body, {"Authorization": f"Bearer {GATEWAY_TOKEN}"}))
    assert resp.status_code == 401
    assert gw.runs == 0


@pytest.mark.asyncio
async def test_no_secret_still_requires_gateway_auth(monkeypatch):
    gw = _Gateway(_hook())
    handler = _handler(gw, monkeypatch)
    body, _ = _delivery(3)
    assert (await handler(_Req(body, {}))).status_code == 401
    resp = await handler(_Req(body, {"Authorization": f"Bearer {GATEWAY_TOKEN}"}))
    assert resp.status_code == 200
    assert gw.runs == 1


@pytest.mark.asyncio
async def test_secret_and_auth_require_both(monkeypatch):
    gw = _Gateway(_hook(secret=SECRET, auth="hook-bearer"))
    handler = _handler(gw, monkeypatch)
    body, headers = _delivery(4)
    assert (await handler(_Req(body, headers))).status_code == 401
    resp = await handler(_Req(body, {**headers, "Authorization": "Bearer hook-bearer"}))
    assert resp.status_code == 200
    assert gw.runs == 1
