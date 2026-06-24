"""Fixtures for PraisonAI <-> PraisonAIUI cross-repo integration tests."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _clear_ui_auth_env(monkeypatch):
    """Prevent host auth env from breaking unauthenticated /run test clients.

    PraisonAIUI's ``create_app()`` enables auth middleware when any of these
    env vars are set, which makes ``POST /run`` return 401 for the
    unauthenticated test clients used by the ``test_aiui_*`` integration tests.
    Mirrors PraisonAIUI's own ``conftest.py`` autouse fixture.

    Note: pytest applies this autouse fixture to every test in this directory
    *and all subdirectories* (``gateway/``, ``acp/``, ``bots/``, etc.). This is
    intentional and safe today because no integration test reads these vars from
    the environment (e.g. gateway tests pass ``auth_token`` explicitly). Any
    future test that needs ``GATEWAY_AUTH_TOKEN`` present in ``os.environ`` must
    set it locally (e.g. via ``monkeypatch.setenv``) rather than relying on the
    ambient environment.
    """
    monkeypatch.delenv("AUTH_ENFORCE", raising=False)
    monkeypatch.delenv("AIUI_URL_TOKEN", raising=False)
    monkeypatch.delenv("GATEWAY_AUTH_TOKEN", raising=False)
