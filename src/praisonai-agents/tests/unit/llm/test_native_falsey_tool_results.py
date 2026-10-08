"""Successful falsey tool results are values, not missing output."""

import json
from copy import deepcopy
from types import SimpleNamespace

import pytest

import praisonaiagents.llm.openai_client as oc
from praisonaiagents.llm.openai_client import OpenAIClient


@pytest.mark.asyncio
@pytest.mark.parametrize('mode', ['sync', 'async', 'stream'])
@pytest.mark.parametrize('value', [0, False, [], {}, '', 1, None])
async def test_native_tool_loop_preserves_falsey_result(monkeypatch, mode, value):
    client = OpenAIClient(api_key='sk-test-not-real')
    tool = SimpleNamespace(id='call-result', type='function',
                           function=SimpleNamespace(name='get_value', arguments='{}'))
    responses = iter([
        SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(
            role='assistant', content=None, tool_calls=[tool]), finish_reason='tool_calls')]),
        SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(
            role='assistant', content='done', tool_calls=None), finish_reason='stop')]),
    ])
    requests = []

    def create(**kwargs):
        requests.append(deepcopy(kwargs))
        return [] if mode == 'stream' else next(responses)

    async def acreate(**kwargs):
        return create(**kwargs)

    client._sync_client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    client._async_client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=acreate)))
    if mode == 'stream':
        monkeypatch.setattr(oc, 'process_stream_chunks', lambda chunks: next(responses))

    executions = []

    def execute(name, arguments, **kwargs):
        executions.append((name, arguments))
        return value

    kwargs = dict(messages=[{'role': 'user', 'content': 'get the value'}],
                  tools=[{'type': 'function', 'function': {'name': 'get_value', 'parameters': {'type': 'object', 'properties': {}}}}],
                  execute_tool_fn=execute, verbose=False, max_iterations=2)
    if mode == 'stream':
        list(client.chat_completion_with_tools_stream(**kwargs))
    elif mode == 'async':
        await client.achat_completion_with_tools(stream=False, **kwargs)
    else:
        client.chat_completion_with_tools(stream=False, **kwargs)
    assert executions == [('get_value', {})]
    assert len(requests) == 2
    tool_messages = [message for message in requests[1]['messages'] if message.get('role') == 'tool']
    assert len(tool_messages) == 1
    expected = 'Function returned an empty output' if value is None else json.dumps(value)
    assert tool_messages[0]['content'] == expected
    assert tool_messages[0]['tool_call_id'] == 'call-result'
