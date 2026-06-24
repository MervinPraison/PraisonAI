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
    """
    monkeypatch.delenv("AUTH_ENFORCE", raising=False)
    monkeypatch.delenv("AIUI_URL_TOKEN", raising=False)
    monkeypatch.delenv("GATEWAY_AUTH_TOKEN", raising=False)
