"""Regression tests for issue #6268: serve agents must not leak exception text."""

import pytest


# --- 2. serve agents never echoes internal exception text --------------------

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from praisonai.cli.features.serve import ServeHandler, _MAX_QUERY_CHARS  # noqa: E402

SECRET = "/etc/secret/path sk-leaked"


@pytest.fixture
def agents_file(tmp_path):
    path = tmp_path / "agents.yaml"
    path.write_text("framework: praisonai\nroles: {}\n")
    return str(path)


@pytest.fixture
def boom_arun(monkeypatch):
    import praisonai

    async def _boom(**kwargs):
        raise RuntimeError(SECRET)

    monkeypatch.setattr(praisonai, "arun", _boom, raising=False)


def _apps(agents_file):
    handler = ServeHandler()
    cfg = {"host": "127.0.0.1", "port": 8765, "file": agents_file}
    agents_app = handler._create_agents_app({**cfg, "path": "/agents"})
    unified_app = handler._create_unified_app(cfg)
    return [(agents_app, "/agents"), (agents_app, "/agents/x"), (unified_app, "/agents")]


def test_agent_failure_does_not_leak_exception_text(agents_file, boom_arun):
    for app, route in _apps(agents_file):
        resp = TestClient(app).post(route, json={"query": "hi"})
        assert resp.status_code == 500, route
        assert SECRET not in resp.text, route
        body = resp.json()
        assert body["error"] == "Internal server error"
        assert body["error_id"]


def test_oversize_query_is_rejected(agents_file, boom_arun):
    big = "x" * (_MAX_QUERY_CHARS + 1)
    for app, route in _apps(agents_file):
        resp = TestClient(app).post(route, json={"query": big})
        if resp.status_code == 422:
            # Pydantic route: must fail on length, not on a missing field.
            types_ = {e["type"] for e in resp.json()["detail"]}
            assert types_ == {"string_too_long"}, (route, resp.json())
        else:
            assert resp.status_code == 413, route
    # Raw-body routes also bound the ``message`` alias.
    for app, route in _apps(agents_file)[1:]:
        resp = TestClient(app).post(route, json={"message": big})
        assert resp.status_code == 413, route
