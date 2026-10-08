"""Completion policy must follow the model sent in the final request."""

from types import SimpleNamespace

import pytest

from praisonaiagents.llm.llm import LLM
from praisonaiagents.thinking.effort import resolve_reasoning_params


@pytest.mark.asyncio
@pytest.mark.parametrize('mode', ['sync', 'async'])
@pytest.mark.parametrize('configured,requested', [
    ('gpt-4o-mini', 'o1'),
    ('o1', 'gpt-4o-mini'),
    ('o1', 'o1'),
    ('gpt-4o-mini', 'gpt-4o-mini'),
    ('o1', 'anthropic/claude-3-7-sonnet'),
    ('anthropic/claude-3-7-sonnet', 'o1'),
])
async def test_public_completion_uses_effective_model(mode, configured, requested):
    llm = LLM(model=configured, reasoning_effort='high')
    requests = []

    def complete(**kwargs):
        requests.append(kwargs)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content='answer'))])

    async def acomplete(**kwargs):
        return complete(**kwargs)

    llm._completion_with_retry = complete
    llm._acompletion_with_retry = acomplete
    kwargs = dict(model=requested, temperature=0.5, top_p=0.5, max_tokens=100,
                  stream=False, verbose=False)
    answer = llm.response('question', **kwargs) if mode == 'sync' else await llm.aresponse('question', **kwargs)
    assert answer == 'answer'
    assert len(requests) == 1
    request = requests[0]
    assert request['model'] == requested
    if requested == 'o1':
        assert 'temperature' not in request
        assert 'top_p' not in request
        assert 'max_tokens' not in request
        assert request['max_completion_tokens'] == 100
    else:
        assert request['temperature'] == 0.5
        assert request['top_p'] == 0.5
        assert request['max_tokens'] == 100
        assert 'max_completion_tokens' not in request
    expected = resolve_reasoning_params('high', requested)
    for name in ('reasoning_effort', 'thinking'):
        assert request.get(name) == expected.get(name)
