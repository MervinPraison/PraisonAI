#!/usr/bin/env python3
"""Issue #5884: ``_dispatch_agent_turn`` must not replay a turn whose entry
point raised an internal ``TypeError``; legacy entry points without
``cancel_token`` are detected from the signature before invoking."""

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(REPO_ROOT / "src" / "praisonai-agents"))

from praisonai_bot.gateway.server import WebSocketGateway

_dispatch = WebSocketGateway._dispatch_agent_turn
_TOKEN = object()


class _FailingSync:
    interrupt_controller = None

    def __init__(self):
        self.calls = []

    def chat(self, content, cancel_token=None):
        self.calls.append(cancel_token)
        raise TypeError("application failure")


class _FailingAsync(_FailingSync):
    async def achat(self, content, cancel_token=None):
        self.calls.append(cancel_token)
        raise TypeError("application failure")


class _LegacySync:
    interrupt_controller = None

    def __init__(self):
        self.calls = 0

    def chat(self, content):
        self.calls += 1
        return f"sync:{content}"


class _LegacyAsync(_LegacySync):
    async def achat(self, content):
        self.calls += 1
        return f"async:{content}"


class _KwargsAsync:
    async def achat(self, content, **kwargs):
        return kwargs.get("cancel_token")


@pytest.mark.asyncio
@pytest.mark.parametrize("cls", [_FailingSync, _FailingAsync])
async def test_internal_type_error_is_not_replayed(cls):
    agent = cls()
    with pytest.raises(TypeError, match="application failure"):
        await _dispatch(agent, "hi", interrupt=_TOKEN)
    assert agent.calls == [_TOKEN]
    assert agent.interrupt_controller is None


@pytest.mark.asyncio
@pytest.mark.parametrize("cls,prefix", [(_LegacySync, "sync"), (_LegacyAsync, "async")])
async def test_legacy_signature_uses_shared_controller(cls, prefix):
    agent = cls()
    assert await _dispatch(agent, "hi", interrupt=_TOKEN) == f"{prefix}:hi"
    assert agent.calls == 1
    assert agent.interrupt_controller is _TOKEN


@pytest.mark.asyncio
async def test_var_keyword_receives_cancel_token():
    assert await _dispatch(_KwargsAsync(), "hi", interrupt=_TOKEN) is _TOKEN
