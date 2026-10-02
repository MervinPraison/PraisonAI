"""Text-part instructions must retain their text through Responses conversion."""

from copy import deepcopy
from types import SimpleNamespace

import pytest

from praisonaiagents.llm.llm import LLM
from praisonaiagents.llm.openai_client import OpenAIClient


@pytest.fixture(autouse=True)
def isolate_responses_endpoint(monkeypatch):
    """Fake Responses clients must not inherit a configured chat endpoint."""
    monkeypatch.delenv('OPENAI_API_BASE', raising=False)
    monkeypatch.delenv('OPENAI_BASE_URL', raising=False)


@pytest.mark.asyncio
@pytest.mark.parametrize('entry', ['llm_sync', 'llm_async', 'client_sync', 'client_async'])
@pytest.mark.parametrize('contents,expected', [
    (['system', [{'type': 'text', 'text': 'developer'}]], 'system\ndeveloper'),
    ([[{'type': 'text', 'text': 'system'}], 'developer'], 'system\ndeveloper'),
    ([[{'type': 'text', 'text': 'first'}, {'type': 'text', 'text': 'second'}]], 'first\nsecond'),
    ([[{'type': 'input_text', 'text': 'system'}], [{'type': 'text', 'text': 'developer'}]], 'system\ndeveloper'),
    (['system', 'developer'], 'system\ndeveloper'),
])
async def test_public_responses_text_part_instructions(entry, contents, expected):
    history = [{'role': 'system' if index == 0 else 'developer', 'content': content}
               for index, content in enumerate(contents)]
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
        answer = llm.get_response('question', **kwargs) if entry == 'llm_sync' else await llm.get_response_async('question', **kwargs)
        assert answer == 'answer'
    else:
        client = OpenAIClient(api_key='sk-test-not-real')
        client._sync_client = SimpleNamespace(responses=SimpleNamespace(create=respond))
        client._async_client = SimpleNamespace(responses=SimpleNamespace(create=arespond))
        messages = history + [{'role': 'user', 'content': 'question'}]
        answer = client.create_completion(messages) if entry == 'client_sync' else await client.acreate_completion(messages)
        assert answer.choices[0].message.content == 'answer'
    assert len(requests) == 1
    assert requests[0]['instructions'] == expected
    assert requests[0]['input'] == [{'role': 'user', 'content': 'question'}]
    assert history == original


@pytest.mark.parametrize('builder', ['llm', 'client'])
@pytest.mark.parametrize('content', [
    [{'type': 'image_url', 'image_url': {'url': 'https://example.com/image.png'}}],
    [{'type': 'text', 'text': None}],
])
def test_unsupported_instruction_parts_are_not_silently_discarded(builder, content):
    messages = [{'role': 'developer', 'content': content}]
    original = deepcopy(messages)
    with pytest.raises(ValueError, match='instructions must contain text parts'):
        if builder == 'llm':
            LLM(model='gpt-4o-mini')._build_responses_params(messages)
        else:
            OpenAIClient(api_key='sk-test-not-real')._build_responses_input(messages, 'gpt-4o-mini')
    assert messages == original
