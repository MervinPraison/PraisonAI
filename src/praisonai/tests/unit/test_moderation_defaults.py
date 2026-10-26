"""Sync and async moderation must select the same model by default."""

import asyncio
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from praisonai.capabilities.moderations import amoderate, moderate


@pytest.mark.parametrize("model", [None, "text-moderation-stable"])
def test_moderation_model_parity(monkeypatch, model):
    response = SimpleNamespace(results=[SimpleNamespace(flagged=False)])
    sync_call = Mock(return_value=response)
    async_call = AsyncMock(return_value=response)
    monkeypatch.setitem(
        sys.modules,
        "litellm",
        SimpleNamespace(moderation=sync_call, amoderation=async_call),
    )
    kwargs = {} if model is None else {"model": model}

    sync_results = moderate("A friendly greeting", **kwargs)
    async_results = asyncio.run(amoderate("A friendly greeting", **kwargs))

    expected_model = model or "omni-moderation-latest"
    expected = {
        "input": "A friendly greeting",
        "model": expected_model,
        "timeout": 600.0,
    }
    sync_call.assert_called_once_with(**expected)
    async_call.assert_awaited_once_with(**expected)
    assert sync_results == async_results
    assert async_results[0].model == expected_model
