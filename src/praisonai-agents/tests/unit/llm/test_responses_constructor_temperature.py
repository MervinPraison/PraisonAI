"""Responses calls honor configured temperature and per-call precedence."""

from types import SimpleNamespace

import pytest

from praisonaiagents.llm.llm import LLM


@pytest.mark.asyncio
@pytest.mark.parametrize('mode', ['sync', 'async'])
@pytest.mark.parametrize('model', ['gpt-4o-mini', 'o1', 'o3'])
@pytest.mark.parametrize('configured,override,expected', [
    (0.0, None, 0.0),
    (0.15, None, 0.15),
    (None, None, None),
    (0.15, 0.75, 0.75),
    (0.15, 0.0, 0.0),
])
async def test_public_responses_temperature_configuration(mode, model, configured, override, expected):
    """Sync and async public requests must preserve zero, defaults and overrides."""
    llm = LLM(model=model, temperature=configured)
    requests = []

    def response(**kwargs):
        requests.append(kwargs)
        return SimpleNamespace(output=[{'type': 'message', 'content': [{'type': 'output_text', 'text': 'answer'}]}])

    async def aresponse(**kwargs):
        return response(**kwargs)

    llm._call_responses_api = response
    llm._call_responses_api_async = aresponse
    kwargs = {'stream': False, 'verbose': False}
    if override is not None:
        kwargs['temperature'] = override
    if mode == 'sync':
        answer = llm.get_response('question', **kwargs)
    else:
        answer = await llm.get_response_async('question', **kwargs)
    assert answer == 'answer'
    assert len(requests) == 1
    if expected is None or model in ('o1', 'o3'):
        assert 'temperature' not in requests[0]
    else:
        assert requests[0]['temperature'] == expected


def test_build_responses_params_drops_reasoning_sampling(monkeypatch):
    """_build_responses_params must strip sampling params for reasoning models."""
    from praisonaiagents.llm import model_capabilities

    monkeypatch.setattr(model_capabilities, 'is_reasoning_model', lambda model: True)
    llm = LLM(model='o1-mini', temperature=0.7, top_p=0.9)
    params = llm._build_responses_params(
        messages=[{'role': 'user', 'content': 'hi'}],
        temperature=0.5,
        top_p=0.8,
    )
    for param in ('temperature', 'top_p', 'presence_penalty',
                  'frequency_penalty', 'logit_bias'):
        assert param not in params


def test_build_responses_params_keeps_sampling_for_standard_model(monkeypatch):
    """Non-reasoning models keep the resolved constructor temperature."""
    from praisonaiagents.llm import model_capabilities

    monkeypatch.setattr(model_capabilities, 'is_reasoning_model', lambda model: False)
    llm = LLM(model='gpt-4o-mini', temperature=0.3)
    params = llm._build_responses_params(
        messages=[{'role': 'user', 'content': 'hi'}],
    )
    assert params['temperature'] == 0.3
