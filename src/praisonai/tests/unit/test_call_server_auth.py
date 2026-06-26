"""Call server agent API must not fail open without CALL_SERVER_TOKEN."""

from __future__ import annotations

import importlib
import os

import pytest

pytest.importorskip("fastapi")


@pytest.mark.asyncio
async def test_verify_token_requires_token_by_default(monkeypatch):
    monkeypatch.delenv("CALL_SERVER_TOKEN", raising=False)
    monkeypatch.delenv("PRAISONAI_CALL_AUTH", raising=False)

    mod = importlib.import_module("praisonai.api.agent_invoke")
    importlib.reload(mod)

    class _Req:
        query_params = {}

    with pytest.raises(Exception) as exc:
        await mod.verify_token(_Req(), authorization=None)
    assert "CALL_SERVER_TOKEN" in str(exc.value)


@pytest.mark.asyncio
async def test_verify_token_optout(monkeypatch):
    monkeypatch.delenv("CALL_SERVER_TOKEN", raising=False)
    monkeypatch.setenv("PRAISONAI_CALL_AUTH", "disabled")
    monkeypatch.setenv("PRAISONAI_CALL_BIND_HOST", "127.0.0.1")

    mod = importlib.import_module("praisonai.api.agent_invoke")
    importlib.reload(mod)

    class _Req:
        query_params = {}

    await mod.verify_token(_Req(), authorization=None)
