"""Explicit zero/False options are distinct from unset (None)."""

import pytest

from praisonaiagents.llm.llm import LLM


OPTIONS = [
    ('seed', 0, 17),
    ('top_p', 0.0, 0.5),
    ('presence_penalty', 0.0, 0.5),
    ('frequency_penalty', 0.0, 0.5),
    ('top_logprobs', 0, 2),
    ('logprobs', False, True),
]


@pytest.mark.parametrize('name,zero,positive', OPTIONS)
@pytest.mark.parametrize('kind', ['zero', 'positive', 'unset', 'override'])
def test_constructor_completion_options_preserve_explicit_values(name, zero, positive, kind):
    value = None if kind == 'unset' else positive if kind == 'positive' else zero
    options = {name: value}
    if name == 'top_logprobs':
        options['logprobs'] = True
    llm = LLM(model='gpt-4o-mini', **options)
    result = llm._build_completion_params(**({name: positive} if kind == 'override' else {}))
    if kind == 'unset':
        assert name not in result
    else:
        assert name in result
        assert result[name] == (positive if kind == 'override' else value)
        if name == 'top_logprobs':
            assert result['logprobs'] is True


@pytest.mark.parametrize('value,override', [(0.0, None), (0.5, None), (None, None), (0.5, 0.0)])
def test_responses_top_p_preserves_zero_and_override(value, override):
    llm = LLM(model='gpt-4o-mini', top_p=value)
    result = llm._build_responses_params(
        [{'role': 'user', 'content': 'question'}],
        **({'top_p': override} if override is not None else {}),
    )
    if value is None and override is None:
        assert 'top_p' not in result
    else:
        assert result['top_p'] == (override if override is not None else value)


def test_zero_top_logprobs_reaches_request_with_logprobs_enabled():
    from litellm import ModelResponse

    llm = LLM(model='gpt-4o-mini', top_logprobs=0, logprobs=True)
    llm._supports_responses_api = lambda: False
    requests = []

    def completion(**kwargs):
        requests.append(kwargs)
        return ModelResponse(choices=[{'message': {'role': 'assistant', 'content': 'answer'}}])

    llm._completion_with_retry = completion
    assert llm.get_response('question', stream=False, verbose=False) == 'answer'
    assert len(requests) == 1
    assert requests[0]['top_logprobs'] == 0
    assert requests[0]['logprobs'] is True


def test_seed_zero_reaches_public_completion_request():
    from litellm import ModelResponse

    llm = LLM(model='gpt-4o-mini', seed=0)
    # Exercise the Chat Completions branch that consumes this builder.
    llm._supports_responses_api = lambda: False
    requests = []

    def completion(**kwargs):
        requests.append(kwargs)
        return ModelResponse(choices=[{'message': {'role': 'assistant', 'content': 'answer'}}])

    llm._completion_with_retry = completion
    assert llm.get_response('question', stream=False, verbose=False) == 'answer'
    assert len(requests) == 1
    assert requests[0]['seed'] == 0
