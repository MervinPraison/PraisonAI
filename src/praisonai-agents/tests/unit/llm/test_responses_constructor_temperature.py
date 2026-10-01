"""Responses calls honor configured temperature and per-call precedence."""

from types import SimpleNamespace

import pytest

from praisonaiagents.llm.llm import LLM


@pytest.mark.asyncio
@pytest.mark.parametrize('mode', ['sync', 'async'])
@pytest.mark.parametrize('configured,override,expected', [
    (0.0, None, 0.0),
    (0.15, None, 0.15),
    (None, None, None),
    (0.15, 0.75, 0.75),
    (0.15, 0.0, 0.0),
])
async def test_public_responses_temperature_configuration(mode, configured, override, expected):
    """Sync and async public requests must preserve zero, defaults and overrides."""
    llm = LLM(model='gpt-4o-mini', temperature=configured)
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
    if expected is None:
        assert 'temperature' not in requests[0]
    else:
        assert requests[0]['temperature'] == expected
