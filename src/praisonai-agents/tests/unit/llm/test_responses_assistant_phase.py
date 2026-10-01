"""Assistant phase survives public Responses history conversion with tools."""

from copy import deepcopy
from types import SimpleNamespace

import pytest

from praisonaiagents.llm.llm import LLM
from praisonaiagents.llm.openai_client import OpenAIClient


@pytest.mark.asyncio
@pytest.mark.parametrize('entry', ['llm_sync', 'llm_async', 'client_sync', 'client_async'])
@pytest.mark.parametrize('phase', ['commentary', 'final_answer', 'absent'])
@pytest.mark.parametrize('with_tools', [True, False])
@pytest.mark.parametrize('parts', [True, False])
async def test_public_responses_preserves_assistant_phase(entry, phase, with_tools, parts):
    message = {'role': 'assistant', 'content': [{'type': 'text', 'text': 'Checking'}] if parts else 'Checking'}
    if phase != 'absent':
        message['phase'] = phase
    history = [message]
    if with_tools:
        message['tool_calls'] = [{
            'id': 'call_1', 'type': 'function',
            'function': {'name': 'lookup', 'arguments': '{"key":"value"}'},
        }]
        history.append({'role': 'tool', 'tool_call_id': 'call_1', 'content': 'found'})
    original = deepcopy(history)
    requests = []

    def respond(**kwargs):
        requests.append(kwargs)
        return SimpleNamespace(output=[{'type': 'message', 'content': [{'type': 'output_text', 'text': 'answer'}]}])

    async def arespond(**kwargs):
        return respond(**kwargs)

    if entry.startswith('llm'):
        llm = LLM(model='gpt-4o-mini')
        llm._call_responses_api = respond
        llm._call_responses_api_async = arespond
        kwargs = dict(chat_history=history, stream=False, verbose=False)
        answer = llm.get_response('continue', **kwargs) if entry == 'llm_sync' else await llm.get_response_async('continue', **kwargs)
        assert answer == 'answer'
    else:
        client = OpenAIClient(api_key='sk-test-not-real')
        client._sync_client = SimpleNamespace(responses=SimpleNamespace(create=respond))
        client._async_client = SimpleNamespace(responses=SimpleNamespace(create=arespond))
        messages = history + [{'role': 'user', 'content': 'continue'}]
        answer = client.create_completion(messages) if entry == 'client_sync' else await client.acreate_completion(messages)
        assert answer.choices[0].message.content == 'answer'

    assert len(requests) == 1
    expected_message = {'role': 'assistant', 'content': [{'type': 'input_text', 'text': 'Checking'}] if parts else 'Checking'}
    if phase != 'absent':
        expected_message['phase'] = phase
    expected_items = [expected_message]
    if with_tools:
        expected_items += [
            {'type': 'function_call', 'call_id': 'call_1', 'name': 'lookup', 'arguments': '{"key":"value"}'},
            {'type': 'function_call_output', 'call_id': 'call_1', 'output': 'found'},
        ]
    expected_items.append({'role': 'user', 'content': 'continue'})
    assert requests[0]['input'] == expected_items
    assert history == original
