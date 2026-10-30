"""The native OpenAI client applies the reasoning-model sampling policy.

OpenAI reasoning models (o1/o3/o4, gpt-5.x) reject sampling parameters such as
``temperature``. ``LLM`` already drops them on both of its paths
(test_responses_reasoning_sampling.py); the native OpenAI client forwarded a
per-call ``temperature`` to the Responses API and again to the Chat Completions
fallback, so ``Agent(llm="o4-mini").chat(..., temperature=0.2)`` failed with
HTTP 400 on both and returned None.
"""
import os
from types import SimpleNamespace

import pytest

os.environ.setdefault("OPENAI_API_KEY", "sk-test-not-real")

from praisonaiagents import Agent
from praisonaiagents.llm.openai_client import OpenAIClient, _normalize_chat_params

SAMPLING = ('temperature', 'top_p', 'presence_penalty', 'frequency_penalty', 'logit_bias')
MESSAGES = [{'role': 'user', 'content': 'question'}]


@pytest.fixture(autouse=True)
def isolate_responses_endpoint(monkeypatch):
    """The Responses path is only taken without a custom endpoint."""
    monkeypatch.delenv('OPENAI_API_BASE', raising=False)
    monkeypatch.delenv('OPENAI_BASE_URL', raising=False)


@pytest.mark.parametrize('model', ['o1', 'o3-mini', 'o4-mini', 'gpt-5-mini'])
@pytest.mark.parametrize('value', [0.0, 0.2])
def test_responses_input_omits_temperature_for_reasoning_models(model, value):
    client = OpenAIClient.__new__(OpenAIClient)
    params = client._build_responses_input(MESSAGES, model, value, None)
    assert 'temperature' not in params


def test_responses_input_keeps_temperature_for_other_models():
    client = OpenAIClient.__new__(OpenAIClient)
    assert client._build_responses_input(MESSAGES, 'gpt-4o-mini', 0.2, None)['temperature'] == 0.2


@pytest.mark.parametrize('model', ['o1', 'o4-mini', 'gpt-5-mini'])
def test_chat_params_omit_sampling_for_reasoning_models(model):
    params = _normalize_chat_params({'model': model, 'messages': MESSAGES, 'max_tokens': 10,
                                     **{key: 0.2 for key in SAMPLING}})
    assert not set(SAMPLING).intersection(params)
    assert params['max_completion_tokens'] == 10


def test_chat_params_keep_sampling_for_other_models():
    params = _normalize_chat_params({'model': 'gpt-4o-mini', 'messages': MESSAGES,
                                     **{key: 0.2 for key in SAMPLING}})
    assert all(params[key] == 0.2 for key in SAMPLING)


def _strict_client(requests):
    """Fake transport that rejects sampling params on a reasoning model, as OpenAI does."""
    def check(kwargs):
        requests.append(kwargs)
        if kwargs.get('temperature') not in (None, 1):
            raise AssertionError('temperature sent to a reasoning model')

    def respond(**kwargs):
        check(kwargs)
        return {'status': 'completed', 'output': [
            {'type': 'message', 'content': [{'type': 'output_text', 'text': 'ok'}]}]}

    async def arespond(**kwargs):
        return respond(**kwargs)

    client = OpenAIClient(api_key='sk-test-not-real')
    client._sync_client = SimpleNamespace(responses=SimpleNamespace(create=respond))
    client._async_client = SimpleNamespace(responses=SimpleNamespace(create=arespond))
    return client


@pytest.mark.asyncio
@pytest.mark.parametrize('mode', ['sync', 'async'])
async def test_public_client_call_omits_temperature(mode):
    requests = []
    client = _strict_client(requests)
    if mode == 'sync':
        answer = client.create_completion(MESSAGES, model='o4-mini', temperature=0.2)
    else:
        answer = await client.acreate_completion(MESSAGES, model='o4-mini', temperature=0.2)
    assert answer.choices[0].message.content == 'ok'
    assert len(requests) == 1 and 'temperature' not in requests[0]


def test_agent_chat_with_temperature_on_reasoning_model():
    requests = []
    agent = Agent(name='t', instructions='x', llm='o4-mini')
    agent._Agent__openai_client = _strict_client(requests)
    assert agent.chat('hi', temperature=0.2) == 'ok'
    assert requests and all('temperature' not in r for r in requests)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
