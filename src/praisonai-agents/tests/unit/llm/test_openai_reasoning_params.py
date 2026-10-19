"""Chat Completions params must not send ``max_tokens: null`` (#5909).

Reasoning models (o-series/gpt-5+) reject an explicit ``null`` for
``max_tokens`` and require ``max_completion_tokens`` instead.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock

from praisonaiagents.llm.openai_client import OpenAIClient


def _client():
    client = OpenAIClient(api_key="test", base_url="http://localhost:1/v1")
    client._sync_client = MagicMock()
    client._async_client = MagicMock()
    client._async_client.chat.completions.create = AsyncMock(return_value="ok")
    return client


def _sent(create):
    return create.call_args.kwargs


def test_unset_max_tokens_and_temperature_are_omitted():
    client = _client()
    client.create_completion(
        messages=[{"role": "user", "content": "hi"}],
        model="o3-mini", temperature=None, max_tokens=None,
    )
    sent = _sent(client._sync_client.chat.completions.create)
    assert "max_tokens" not in sent
    assert "max_completion_tokens" not in sent
    assert "temperature" not in sent


def test_async_reasoning_model_maps_max_tokens():
    client = _client()
    asyncio.run(client.acreate_completion(
        messages=[{"role": "user", "content": "hi"}],
        model="openai/gpt-5-mini", temperature=None, max_tokens=100,
    ))
    sent = _sent(client._async_client.chat.completions.create)
    assert "max_tokens" not in sent
    assert sent["max_completion_tokens"] == 100


def test_explicit_max_completion_tokens_wins():
    client = _client()
    client.create_completion(
        messages=[{"role": "user", "content": "hi"}],
        model="o3-mini", max_tokens=100, max_completion_tokens=50,
    )
    sent = _sent(client._sync_client.chat.completions.create)
    assert "max_tokens" not in sent
    assert sent["max_completion_tokens"] == 50


def test_non_reasoning_model_keeps_max_tokens():
    client = _client()
    client.create_completion(
        messages=[{"role": "user", "content": "hi"}],
        model="gpt-4o-mini", temperature=0.2, max_tokens=100,
    )
    sent = _sent(client._sync_client.chat.completions.create)
    assert sent["max_tokens"] == 100
    assert sent["temperature"] == 0.2
    assert "max_completion_tokens" not in sent


def test_streaming_path_omits_null_max_tokens():
    client = _client()
    client._sync_client.chat.completions.create.return_value = iter(())
    client.process_stream_response(
        messages=[{"role": "user", "content": "hi"}],
        model="o3-mini", temperature=None, max_tokens=None,
    )
    sent = _sent(client._sync_client.chat.completions.create)
    assert "max_tokens" not in sent
    assert "temperature" not in sent


async def _empty_stream():
    return
    yield


def test_async_streaming_path_maps_max_tokens():
    client = _client()
    client._async_client.chat.completions.create = AsyncMock(return_value=_empty_stream())
    asyncio.run(client.process_stream_response_async(
        messages=[{"role": "user", "content": "hi"}],
        model="o3-mini", temperature=None, max_tokens=100,
    ))
    sent = _sent(client._async_client.chat.completions.create)
    assert "max_tokens" not in sent
    assert "temperature" not in sent
    assert sent["max_completion_tokens"] == 100


def test_tools_streaming_path_maps_max_tokens():
    client = _client()
    client._sync_client.chat.completions.create.return_value = iter(())
    list(client.chat_completion_with_tools_stream(
        messages=[{"role": "user", "content": "hi"}],
        model="o3-mini", temperature=None, max_tokens=100,
    ))
    sent = _sent(client._sync_client.chat.completions.create)
    assert "max_tokens" not in sent
    assert "temperature" not in sent
    assert sent["max_completion_tokens"] == 100
