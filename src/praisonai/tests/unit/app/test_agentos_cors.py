"""AgentOS CORS must never pair a wildcard origin with credentials (#6094)."""

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from praisonai import AgentOS  # noqa: E402


def _preflight(origins):
    app = AgentOS(name="t", agents=[], cors_origins=origins).get_app()
    return TestClient(app).get(
        "/health", headers={"Origin": "https://evil.example", "Cookie": "s=1"}
    )


def test_wildcard_origin_disables_credentials():
    resp = _preflight(["*"])
    assert resp.headers.get("access-control-allow-origin") == "*"
    assert "access-control-allow-credentials" not in resp.headers


def test_explicit_origin_keeps_credentials():
    app = AgentOS(name="t", agents=[], cors_origins=["https://ok.example"]).get_app()
    resp = TestClient(app).get("/health", headers={"Origin": "https://ok.example"})
    assert resp.headers.get("access-control-allow-origin") == "https://ok.example"
    assert resp.headers.get("access-control-allow-credentials") == "true"
