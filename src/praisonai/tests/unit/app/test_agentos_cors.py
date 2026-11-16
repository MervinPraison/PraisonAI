"""AgentOS CORS must never pair a wildcard origin with credentials (#6094)."""

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from praisonai import AgentOS  # noqa: E402


def _get(origins, origin, **headers):
    app = AgentOS(name="t", agents=[], cors_origins=origins).get_app()
    return TestClient(app).get("/health", headers={"Origin": origin, **headers})


def test_wildcard_origin_disables_credentials():
    # Older Starlette reflects the Origin whenever a cookie is present, so only
    # the credentials header is version-independent here.
    resp = _get(["*"], "https://evil.example", Cookie="s=1")
    assert "access-control-allow-credentials" not in resp.headers

    resp = _get(["*"], "https://evil.example")
    assert resp.headers.get("access-control-allow-origin") == "*"
    assert "access-control-allow-credentials" not in resp.headers


def test_explicit_origin_keeps_credentials():
    resp = _get(["https://ok.example"], "https://ok.example")
    assert resp.headers.get("access-control-allow-origin") == "https://ok.example"
    assert resp.headers.get("access-control-allow-credentials") == "true"
