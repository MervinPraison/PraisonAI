"""Responses history conversion preserves SDK function-call payloads."""

from types import SimpleNamespace

import pytest
from openai.types.chat import ChatCompletionMessageToolCall

from praisonaiagents.llm.llm import LLM
from praisonaiagents.llm.openai_client import OpenAIClient


def tool_call(shape):
    """Return equivalent nested and flattened supported call shapes."""
    sdk = ChatCompletionMessageToolCall(
        id='call_1', type='function', function={'name': 'lookup', 'arguments': '{"key":"value"}'},
    )
    if shape == 'sdk':
        return sdk
    if shape == 'dict':
        return sdk.model_dump()
    if shape == 'mixed':
        return {'id': sdk.id, 'function': sdk.function}
    return SimpleNamespace(id=sdk.id, name=sdk.function.name, arguments=sdk.function.arguments)


@pytest.mark.parametrize('shape', ['sdk', 'dict', 'mixed', 'flat'])
def test_tool_history_conversion_preserves_name_arguments_and_result(shape):
    """Nested SDK objects must produce the same items as serialized dictionaries."""
    llm = LLM(model='gpt-4o-mini')
    result = llm._build_responses_params(messages=[
        {'role': 'assistant', 'content': 'Checking', 'tool_calls': [tool_call(shape)]},
        {'role': 'tool', 'tool_call_id': 'call_1', 'content': 'found'},
    ])
    assert result['input'] == [
        {'role': 'assistant', 'content': 'Checking'},
        {'type': 'function_call', 'call_id': 'call_1', 'name': 'lookup', 'arguments': '{"key":"value"}'},
        {'type': 'function_call_output', 'call_id': 'call_1', 'output': 'found'},
    ]


def test_public_response_preserves_sdk_tool_call_history():
    """Public chat_history must reach the Responses boundary without payload loss."""
    llm = LLM(model='gpt-4o-mini')
    requests = []

    def response(**kwargs):
        requests.append(kwargs)
        return SimpleNamespace(output=[{'type': 'message', 'content': [{'type': 'output_text', 'text': 'answer'}]}])

    llm._call_responses_api = response
    assert llm.get_response('continue', chat_history=[
        {'role': 'assistant', 'content': None, 'tool_calls': [tool_call('sdk')]},
        {'role': 'tool', 'tool_call_id': 'call_1', 'content': 'found'},
    ], stream=False, verbose=False) == 'answer'
    call = next(item for item in requests[0]['input'] if item.get('type') == 'function_call')
    assert call['name'] == 'lookup'
    assert call['arguments'] == '{"key":"value"}'


@pytest.mark.asyncio
@pytest.mark.parametrize('mode', ['sync', 'async'])
@pytest.mark.parametrize('shape', ['sdk', 'dict', 'mixed', 'flat'])
async def test_public_client_preserves_tool_call_history(mode, shape):
    client = OpenAIClient(api_key='sk-test-not-real')
    requests = []

    def response(**kwargs):
        requests.append(kwargs)
        return SimpleNamespace(output=[{'type': 'message', 'content': [{'type': 'output_text', 'text': 'answer'}]}])

    async def aresponse(**kwargs):
        return response(**kwargs)

    client._sync_client = SimpleNamespace(responses=SimpleNamespace(create=response))
    client._async_client = SimpleNamespace(responses=SimpleNamespace(create=aresponse))
    messages = [
        {'role': 'assistant', 'content': 'Checking', 'tool_calls': [tool_call(shape)]},
        {'role': 'tool', 'tool_call_id': 'call_1', 'content': 'found'},
        {'role': 'user', 'content': 'continue'},
    ]
    answer = client.create_completion(messages) if mode == 'sync' else await client.acreate_completion(messages)
    assert answer.choices[0].message.content == 'answer'
    assert len(requests) == 1
    assert requests[0]['input'] == [
        {'role': 'assistant', 'content': 'Checking'},
        {'type': 'function_call', 'call_id': 'call_1', 'name': 'lookup', 'arguments': '{"key":"value"}'},
        {'type': 'function_call_output', 'call_id': 'call_1', 'output': 'found'},
        {'role': 'user', 'content': 'continue'},
    ]
