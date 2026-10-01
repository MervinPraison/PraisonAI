"""Responses sampling policy follows the model actually sent to the provider."""

from types import SimpleNamespace

import pytest

from praisonaiagents.llm.llm import LLM


@pytest.mark.asyncio
@pytest.mark.parametrize('mode', ['sync', 'async'])
@pytest.mark.parametrize('configured,requested,keep_sampling', [
    ('o1', 'gpt-4o-mini', True),
    ('gpt-4o-mini', 'o1', False),
    ('o3', 'gpt-4o-mini', True),
    ('gpt-4o-mini', 'o3', False),
    ('o1', 'o1', False),
    ('gpt-4o-mini', 'gpt-4o-mini', True),
])
async def test_public_responses_sampling_uses_effective_model(mode, configured, requested, keep_sampling):
    """Model overrides must neither discard valid sampling nor regain invalid fields."""
    llm = LLM(model=configured)
    requests = []

    def response(**kwargs):
        requests.append(kwargs)
        return SimpleNamespace(output=[{'type': 'message', 'content': [{'type': 'output_text', 'text': 'answer'}]}])

    async def aresponse(**kwargs):
        return response(**kwargs)

    llm._call_responses_api = response
    llm._call_responses_api_async = aresponse
    kwargs = {'stream': False, 'verbose': False, 'model': requested, 'temperature': 0.5, 'top_p': 0.5}
    answer = llm.get_response('question', **kwargs) if mode == 'sync' else await llm.get_response_async('question', **kwargs)
    assert answer == 'answer'
    assert len(requests) == 1
    assert requests[0]['model'] == requested
    if keep_sampling:
        assert requests[0]['temperature'] == 0.5
        assert requests[0]['top_p'] == 0.5
    else:
        assert 'temperature' not in requests[0]
        assert 'top_p' not in requests[0]
