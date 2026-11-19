"""Recipe serve / registry serve: shared bind guard, cross-site refusal,
and run options that only the server config can widen."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

pytest.importorskip("starlette")
from starlette.testclient import TestClient

import praisonai.recipe as recipe_pkg
from praisonai.recipe import serve as S
from praisonai.recipe import server as RS


class _Res:
    ok = True
    status = "success"

    def to_dict(self):
        return {"ok": True}


@pytest.fixture
def calls(monkeypatch):
    seen = []
    monkeypatch.setattr(recipe_pkg, "run", lambda name, **kw: seen.append(kw.get("options")) or _Res())
    monkeypatch.delenv("PRAISONAI_API_KEY", raising=False)
    return seen


def _post(client, headers):
    body = {"recipe": "r", "input": {}, "options": {"allow_dangerous_tools": True, "x": 1}}
    return client.post("/v1/recipes/run", content=json.dumps(body), headers=headers)


def test_keyless_app_refuses_cross_site_simple_post(calls):
    resp = _post(TestClient(S.create_app({})),
                 {"Content-Type": "text/plain", "Origin": "http://foreign.example"})
    assert resp.status_code == 403
    assert calls == []


def test_request_cannot_allow_dangerous_tools(calls):
    resp = _post(TestClient(S.create_app({})), {"Content-Type": "application/json"})
    assert resp.status_code == 200
    assert calls == [{"x": 1}]


def test_server_config_can_allow_dangerous_tools(calls):
    _post(TestClient(S.create_app({"allow_dangerous_tools": True})), {})
    assert calls[-1]["allow_dangerous_tools"] is True


def test_serve_public_bind_without_auth_refuses(monkeypatch):
    monkeypatch.delenv("PRAISONAI_API_KEY", raising=False)
    with patch("uvicorn.run") as run:
        with pytest.raises(ValueError, match="refuses to bind non-loopback"):
            S.serve(host="0.0.0.0", config={})
    run.assert_not_called()


def test_serve_public_bind_with_api_key_starts():
    with patch("uvicorn.run") as run:
        S.serve(host="0.0.0.0", config={"auth": "api-key", "api_key": "k"})
    assert run.call_args.kwargs["host"] == "0.0.0.0"


def test_serve_loopback_guards_host_header():
    with patch("uvicorn.run") as run:
        S.serve(host="127.0.0.1", config={})
    served = run.call_args.args[0]
    assert TestClient(served, base_url="http://foreign.example").get("/health").status_code == 403


@pytest.mark.parametrize("kw, ok", [({}, False), ({"token": "t"}, True), ({"read_only": True}, True)])
def test_registry_public_bind_needs_token_or_read_only(tmp_path, kw, ok):
    class _Srv:
        def serve_forever(self):
            pass

    with patch("wsgiref.simple_server.make_server", return_value=_Srv()) as make:
        if ok:
            RS.run_server(host="0.0.0.0", port=1, registry_path=Path(tmp_path), **kw)
            make.assert_called_once()
        else:
            with pytest.raises(ValueError, match="--token"):
                RS.run_server(host="0.0.0.0", port=1, registry_path=Path(tmp_path), **kw)
            make.assert_not_called()
