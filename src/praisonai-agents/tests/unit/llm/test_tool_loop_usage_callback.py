"""The OpenAI-client tool loop reports every billed call except the final one (F-07)."""

from types import SimpleNamespace

import pytest

from praisonaiagents.llm.openai_client import OpenAIClient
from praisonaiagents.llm.unified_adapters import OpenAIAdapter


def _resp(tool_calls=None, content=None):
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(
            role='assistant', content=content, tool_calls=tool_calls),
            finish_reason='tool_calls' if tool_calls else 'stop')],
        usage=SimpleNamespace(prompt_tokens=7, completion_tokens=3, total_tokens=10),
    )


def _run(mode, responses):
    client = OpenAIClient(api_key='sk-test-not-real')
    requests = []

    def create(**kwargs):
        requests.append(kwargs)
        return next(responses)

    async def acreate(**kwargs):
        return create(**kwargs)

    client._sync_client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    client._async_client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=acreate)))
    reported = []
    kwargs = dict(
        messages=[{'role': 'user', 'content': 'hi'}],
        tools=[{'type': 'function', 'function': {'name': 'lookup', 'parameters': {'type': 'object', 'properties': {}}}}],
        execute_tool_fn=lambda name, args, **kw: 'ok', verbose=False, max_iterations=3,
        stream=False, usage_callback=reported.append,
    )
    return client, kwargs, reported, requests


async def _call(client, kwargs, mode):
    # The agent's sync route is OpenAIAdapter.chat_completion, which runs the async loop.
    if mode == 'async':
        return await client.achat_completion_with_tools(**kwargs)
    messages = kwargs.pop('messages')
    return OpenAIAdapter(client).chat_completion(messages, **kwargs)


def _tool():
    return SimpleNamespace(id='c1', type='function', function=SimpleNamespace(name='lookup', arguments='{}'))


@pytest.mark.asyncio
@pytest.mark.parametrize('mode', ['sync', 'async'])
async def test_reports_only_calls_before_the_final_one(mode):
    first, last = _resp([_tool()]), _resp(content='done')
    client, kwargs, reported, requests = _run(mode, iter([first, last]))
    result = await _call(client, kwargs, mode)
    assert result is last
    assert reported == [first]
    assert all('usage_callback' not in r for r in requests)


@pytest.mark.asyncio
@pytest.mark.parametrize('mode', ['sync', 'async'])
async def test_reports_earlier_call_when_a_later_round_returns_nothing(mode):
    first = _resp([_tool()])
    client, kwargs, reported, _ = _run(mode, iter([first, None]))
    result = await _call(client, kwargs, mode)
    assert result is None
    assert reported == [first]
