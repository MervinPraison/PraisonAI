"""Regression test for GHSA-6rmh-7xcm-cpxj.

The shipped legacy ``api_server.py`` previously had ``AUTH_ENABLED = False``
hard-coded, so ``GET /agents`` and ``POST /chat`` were reachable without
any token. The fix flips authentication ON by default and requires
``PRAISONAI_API_AUTH=disabled`` for the legacy fail-open behaviour.
"""

from __future__ import annotations

import importlib
import os
import sys
import types
from pathlib import Path

import pytest

# api_server.py uses Flask, which is an optional deploy dependency.
pytest.importorskip("flask")
pytest.importorskip("flask_cors")


PKG_ROOT = Path(__file__).resolve().parents[2]
API_SERVER_PATH = PKG_ROOT / "api_server.py"


@pytest.fixture
def import_api_server(monkeypatch):
    # Stub the praisonai package import so the server module loads in
    # isolation against a controlled PraisonAI workflow class.
    stub = types.ModuleType("praisonai")

    class _DummyPraisonAI:
        def __init__(self, agent_file="agents.yaml"):
            self.agent_file = agent_file
        def run(self):
            return {"ran": True, "agent_file": self.agent_file}

    stub.PraisonAI = _DummyPraisonAI
    monkeypatch.setitem(sys.modules, "praisonai", stub)

    def _load(env=None):
        if env:
            for k, v in env.items():
                monkeypatch.setenv(k, v)
        spec = importlib.util.spec_from_file_location("api_server_under_test", API_SERVER_PATH)
        module = importlib.util.module_from_spec(spec)
        # Avoid clobbering between tests.
        sys.modules.pop("api_server_under_test", None)
        spec.loader.exec_module(module)
        return module

    return _load


def test_auth_enabled_by_default(import_api_server, monkeypatch):
    monkeypatch.delenv("PRAISONAI_API_AUTH", raising=False)
    monkeypatch.delenv("PRAISONAI_API_TOKEN", raising=False)
    mod = import_api_server()

    assert mod.AUTH_ENABLED is True, "auth must be ON by default"
    assert mod.AUTH_TOKEN, "a bearer token must be set"

    client = mod.app.test_client()
    # Anonymous request must be rejected.
    assert client.get("/agents").status_code == 401
    assert client.post("/chat", json={"message": "hi"}).status_code == 401

    # Authenticated request must succeed.
    headers = {"Authorization": f"Bearer {mod.AUTH_TOKEN}"}
    assert client.get("/agents", headers=headers).status_code == 200


def test_explicit_optout_still_works(import_api_server, monkeypatch):
    monkeypatch.delenv("PRAISONAI_API_TOKEN", raising=False)
    mod = import_api_server({"PRAISONAI_API_AUTH": "disabled"})
    assert mod.AUTH_ENABLED is False
    client = mod.app.test_client()
    assert client.get("/agents").status_code == 200


def test_health_remains_unauthenticated(import_api_server, monkeypatch):
    monkeypatch.delenv("PRAISONAI_API_AUTH", raising=False)
    monkeypatch.delenv("PRAISONAI_API_TOKEN", raising=False)
    mod = import_api_server()
    client = mod.app.test_client()
    assert client.get("/health").status_code == 200
