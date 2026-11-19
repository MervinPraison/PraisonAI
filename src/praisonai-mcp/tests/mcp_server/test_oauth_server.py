"""The built-in OAuth 2.1 authorization server, end to end over HTTP.

Everything runs in-process (Starlette TestClient); client metadata documents
are stubbed, so no network call or real credential is involved.
"""

from __future__ import annotations

import base64
import hashlib
import re
import time
from urllib.parse import parse_qs, urlparse

import pytest

pytest.importorskip("starlette")
pytest.importorskip("httpx")

from starlette.testclient import TestClient  # noqa: E402

from praisonai_mcp.mcp_server.auth.server import OAuthServer, redirect_matches  # noqa: E402
from praisonai_mcp.mcp_server.server import MCPServer  # noqa: E402
from praisonai_mcp.mcp_server.transports.http_stream import HTTPStreamTransport  # noqa: E402

ISSUER = "http://testserver"
OWNER = "owner-key-for-tests"
VERIFIER = "v" * 64
CHALLENGE = base64.urlsafe_b64encode(hashlib.sha256(VERIFIER.encode()).digest()).rstrip(b"=").decode()
CIMD_URL = "https://vscode.dev/oauth/client-metadata.json"


def _cimd(url):
    assert url == CIMD_URL
    return {"client_id": url, "client_name": "Visual Studio Code", "redirect_uris": ["http://127.0.0.1:33418/"]}


@pytest.fixture
def env(tmp_path):
    oauth = OAuthServer(ISSUER, ISSUER + "/mcp", owner_key=OWNER, store_path=tmp_path / "oauth.json", fetch_metadata=_cimd)
    transport = HTTPStreamTransport(server=MCPServer(name="t"), host="0.0.0.0", allowed_origins=[], oauth=oauth)
    return oauth, TestClient(transport._create_app(), follow_redirects=False), tmp_path / "oauth.json"


def _register(client, uri="http://localhost:8787/callback", name="Cursor"):
    r = client.post("/oauth/register", json={"client_name": name, "redirect_uris": [uri]})
    assert r.status_code == 201
    return r.json()["client_id"]


def _authorize(client, cid, redirect="http://localhost:8787/callback", **extra):
    q = {"response_type": "code", "client_id": cid, "redirect_uri": redirect, "state": "s1",
         "code_challenge": CHALLENGE, "code_challenge_method": "S256", "resource": ISSUER + "/mcp", **extra}
    return client.get("/oauth/authorize", params=q)


def _form(page):
    rid = re.search(r"name=rid value='([^']+)'", page).group(1)
    csrf = re.search(r"name=csrf value='([^']+)'", page).group(1)
    return {"rid": rid, "csrf": csrf}


def _sign_in(client, cid, scopes=("tools:read", "tools:call"), redirect="http://localhost:8787/callback"):
    page = _authorize(client, cid, redirect).text
    r = client.post("/oauth/authorize", data={**_form(page), "owner_key": OWNER, "decision": "allow",
                                              "scope": list(scopes), "lifetime": "30d"})
    assert r.status_code == 303, r.text
    loc = urlparse(r.headers["location"])
    code = parse_qs(loc.query)["code"][0]
    tok = client.post("/oauth/token", data={"grant_type": "authorization_code", "code": code, "client_id": cid,
                                            "redirect_uri": redirect, "code_verifier": VERIFIER,
                                            "resource": ISSUER + "/mcp"})
    assert tok.status_code == 200, tok.text
    return tok.json()


def _mcp(client, token, method="tools/list"):
    return client.post("/mcp", headers={"Authorization": f"Bearer {token}", "Accept": "application/json, text/event-stream"},
                       json={"jsonrpc": "2.0", "id": 1, "method": method, "params": {"name": "x", "arguments": {}}})


def test_unauthenticated_call_points_to_the_metadata(env):
    _, client, _ = env
    r = client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
    assert r.status_code == 401
    assert 'resource_metadata="http://testserver/.well-known/oauth-protected-resource/mcp"' in r.headers["www-authenticate"]
    prm = client.get("/.well-known/oauth-protected-resource/mcp").json()
    assert prm["resource"] == ISSUER + "/mcp" and prm["authorization_servers"] == [ISSUER]
    asm = client.get("/.well-known/oauth-authorization-server").json()
    assert asm["code_challenge_methods_supported"] == ["S256"]
    assert asm["client_id_metadata_document_supported"] is True
    assert asm["device_authorization_endpoint"].endswith("/oauth/device")


def test_full_sign_in_scopes_and_refresh_rotation(env):
    oauth, client, store = env
    cid = _register(client)
    page = _authorize(client, cid).text
    assert "On this device" in page and "Run your agents and tools" in page
    tok = _sign_in(client, cid, scopes=("tools:read",))
    assert tok["scope"] == "tools:read" and tok["refresh_token"] != tok["access_token"]
    assert _mcp(client, tok["access_token"]).status_code == 200
    assert _mcp(client, tok["access_token"], "tools/call").status_code == 403  # read-only grant
    text = store.read_text()
    assert tok["access_token"] not in text and tok["refresh_token"] not in text  # hashes only
    assert store.stat().st_mode & 0o777 == 0o600

    new = client.post("/oauth/token", data={"grant_type": "refresh_token", "refresh_token": tok["refresh_token"],
                                            "client_id": cid}).json()
    assert new["refresh_token"] != tok["refresh_token"]
    replay = client.post("/oauth/token", data={"grant_type": "refresh_token", "refresh_token": tok["refresh_token"]})
    assert replay.json()["error"] == "invalid_grant" and "reuse" in replay.json()["error_description"]
    assert _mcp(client, new["access_token"]).status_code == 401  # the whole grant was revoked


def test_wrong_owner_key_wrong_verifier_and_deny(env):
    _, client, _ = env
    cid = _register(client)
    page = _authorize(client, cid).text
    bad = client.post("/oauth/authorize", data={**_form(page), "owner_key": "nope", "decision": "allow", "scope": ["tools:read"]})
    assert bad.status_code == 401 and "not right" in bad.text
    deny = client.post("/oauth/authorize", data={**_form(_authorize(client, cid).text), "decision": "deny"})
    q = parse_qs(urlparse(deny.headers["location"]).query)
    assert q["error"] == ["access_denied"] and q["state"] == ["s1"]
    page = _authorize(client, cid).text
    r = client.post("/oauth/authorize", data={**_form(page), "owner_key": OWNER, "decision": "allow", "scope": ["tools:read"]})
    code = parse_qs(urlparse(r.headers["location"]).query)["code"][0]
    wrong = client.post("/oauth/token", data={"grant_type": "authorization_code", "code": code, "client_id": cid,
                                              "code_verifier": "w" * 64})
    assert wrong.json()["error"] == "invalid_grant"


def test_authorize_request_errors(env):
    _, client, _ = env
    cid = _register(client)
    no_pkce = client.get("/oauth/authorize", params={"response_type": "code", "client_id": cid, "state": "s",
                                                    "redirect_uri": "http://localhost:8787/callback"})
    assert parse_qs(urlparse(no_pkce.headers["location"]).query)["error"] == ["invalid_request"]
    other = _authorize(client, cid, resource="https://elsewhere.example/mcp")
    assert parse_qs(urlparse(other.headers["location"]).query)["error"] == ["invalid_target"]
    assert _authorize(client, cid, redirect="https://evil.example/cb").status_code == 400
    assert _authorize(client, cid, redirect="http://localhost:18787/callback").status_code == 200  # any loopback port
    assert client.post("/oauth/register", json={"redirect_uris": ["http://evil.example/cb"]}).status_code == 400


def test_known_and_unknown_clients(env):
    _, client, _ = env
    page = _authorize(client, CIMD_URL, redirect="http://127.0.0.1:33418/").text
    assert "Connect VS Code" in page and "Verified" in page and "could not verify" not in page
    cid = _register(client, "https://www.cursor.com/agents/mcp/oauth/callback", "Cursor")
    assert "Verified" in _authorize(client, cid, redirect="https://www.cursor.com/agents/mcp/oauth/callback").text
    cid = _register(client, "https://odd.example/cb", "Mystery")
    page = _authorize(client, cid, redirect="https://odd.example/cb")
    assert "Not verified" in page.text and "odd.example" in page.text
    assert page.headers["x-frame-options"] == "DENY"


def test_device_flow(env):
    _, client, _ = env
    cid = _register(client)
    d = client.post("/oauth/device", data={"client_id": cid, "scope": "tools:read tools:call"}).json()
    poll = {"grant_type": "urn:ietf:params:oauth:grant-type:device_code", "device_code": d["device_code"], "client_id": cid}
    assert client.post("/oauth/token", data=poll).json()["error"] in ("authorization_pending", "slow_down")
    page = client.get("/oauth/device/verify", params={"user_code": d["user_code"]}).text
    assert "Connect Cursor" in page
    done = client.post("/oauth/device/verify", data={**_form(page), "owner_key": OWNER, "decision": "allow",
                                                     "scope": ["tools:read", "tools:call"]})
    assert done.status_code == 200 and "Connected" in done.text
    tok = client.post("/oauth/token", data=poll).json()
    assert _mcp(client, tok["access_token"]).status_code == 200
    assert client.get("/oauth/device/verify", params={"user_code": "XXXX-XXXX"}).status_code == 400


def test_connected_apps_list_and_revoke(env):
    oauth, client, _ = env
    cid = _register(client)
    tok = _sign_in(client, cid)
    client.cookies.clear()  # the consent page signed the owner in with a cookie
    assert client.get("/oauth/apps").status_code == 401
    apps = client.get("/oauth/apps", headers={"Authorization": f"Bearer {OWNER}"}).json()["apps"]
    assert apps[0]["client"] == "Cursor" and apps[0]["trust"] == "local"
    r = client.post(f"/oauth/apps/{apps[0]['id']}/revoke", headers={"Authorization": f"Bearer {OWNER}"})
    assert r.json() == {"revoked": True}
    assert _mcp(client, tok["access_token"]).status_code == 401
    tok = _sign_in(client, cid)
    client.post("/oauth/revoke", data={"token": tok["refresh_token"]})
    assert _mcp(client, tok["access_token"]).status_code == 401


def test_grant_lifetime_and_persistence(env, tmp_path):
    oauth, client, store = env
    cid = _register(client)
    tok = _sign_in(client, cid)
    again = OAuthServer(ISSUER, ISSUER + "/mcp", owner_key=OWNER, store_path=store)
    assert again.validate_header(f"Bearer {tok['access_token']}")[0]  # survives a restart
    grant = next(iter(again._data["grants"].values()))
    grant["expires"] = time.time() - 1
    assert again.apps() == []


def test_redirect_matching():
    reg = ["http://127.0.0.1:33418/", "cursor://anysphere.cursor-mcp/oauth/callback"]
    assert redirect_matches(reg, "http://127.0.0.1:5555/")
    assert not redirect_matches(reg, "http://127.0.0.1:5555/other")
    assert not redirect_matches(reg, "http://localhost:33418/")  # localhost and 127.0.0.1 differ
    assert redirect_matches(reg, "cursor://anysphere.cursor-mcp/oauth/callback")


def test_serve_turns_oauth_on_only_off_localhost(monkeypatch, tmp_path):
    import argparse

    from praisonai_mcp.mcp_server.cli import MCPServerCLI

    monkeypatch.setenv("PRAISONAI_HOME", str(tmp_path))
    ns = lambda host, oauth=False: argparse.Namespace(host=host, port=8080, endpoint="/mcp", oauth=oauth, issuer=None)  # noqa: E731
    cli = MCPServerCLI()
    assert cli._oauth_server(ns("127.0.0.1")) is None
    assert cli._oauth_server(ns("127.0.0.1", oauth=True)) is not None
    remote = cli._oauth_server(ns("0.0.0.0"))
    assert remote.resource == "http://0.0.0.0:8080/mcp"
