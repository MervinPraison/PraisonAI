"""Responses honors the reasoning-model sampling policy of Chat Completions."""

from types import SimpleNamespace

import pytest

from praisonaiagents.llm.llm import LLM


@pytest.mark.parametrize('model', ['o1', 'o3', 'openai/o3', 'azure/o1'])
@pytest.mark.parametrize('value', [0.0, 0.5])
@pytest.mark.parametrize('source', ['constructor', 'override'])
def test_reasoning_responses_omit_sampling_after_overrides(model, value, source):
    """Neither constructor settings nor overrides may reintroduce sampling."""
    options = {'top_p': value, 'temperature': value, 'presence_penalty': value,
               'frequency_penalty': value, 'logit_bias': {'1': 1}}
    llm = LLM(model=model, **(options if source == 'constructor' else {}))
    params = llm._build_responses_params(
        [{'role': 'user', 'content': 'question'}],
        **(options if source == 'override' else {}),
    )
    assert not set(options).intersection(params)


@pytest.mark.parametrize('value', [0.0, 0.5])
@pytest.mark.parametrize('source', ['constructor', 'override'])
def test_non_reasoning_responses_keep_sampling(value, source):
    """Ordinary models still retain configured sampling parameters."""
    llm = LLM(model='gpt-4o-mini', **({'top_p': value} if source == 'constructor' else {}))
    params = llm._build_responses_params(
        [{'role': 'user', 'content': 'question'}],
        **({'top_p': value, 'temperature': value} if source == 'override' else {}),
    )
    assert params['top_p'] == value
    if source == 'override':
        assert params['temperature'] == value


@pytest.mark.asyncio
@pytest.mark.parametrize('mode', ['sync', 'async'])
async def test_public_reasoning_responses_omit_sampling(mode):
    """Public requests must apply the policy before reaching either transport."""
    llm = LLM(model='o1', top_p=0.0)
    requests = []

    def response(**kwargs):
        requests.append(kwargs)
        return SimpleNamespace(output=[{'type': 'message', 'content': [{'type': 'output_text', 'text': 'answer'}]}])

    async def aresponse(**kwargs):
        return response(**kwargs)

    llm._call_responses_api = response
    llm._call_responses_api_async = aresponse
    kwargs = {'stream': False, 'verbose': False, 'temperature': 0.5, 'top_p': 0.0}
    answer = llm.get_response('question', **kwargs) if mode == 'sync' else await llm.get_response_async('question', **kwargs)
    assert answer == 'answer'
    assert len(requests) == 1
    assert 'top_p' not in requests[0]
    assert 'temperature' not in requests[0]
