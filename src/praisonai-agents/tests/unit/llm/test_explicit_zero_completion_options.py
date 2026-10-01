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
    llm = LLM(model='gpt-4o-mini', **{name: value})
    result = llm._build_completion_params(**({name: positive} if kind == 'override' else {}))
    if kind == 'unset':
        assert name not in result
    else:
        assert name in result
        assert result[name] == (positive if kind == 'override' else value)


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
