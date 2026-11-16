"""An unset LLM timeout is bounded; an explicit None/0 opts out (Issue #5968)."""

import pytest

from praisonaiagents.llm.llm import LLM, _DEFAULT_LLM_TIMEOUT_S


def _params(llm):
    return (
        llm._build_completion_params(),
        llm._build_responses_params([{'role': 'user', 'content': 'hi'}]),
    )


def test_unset_timeout_uses_finite_default():
    llm = LLM(model='gpt-4o-mini')
    assert llm.timeout == _DEFAULT_LLM_TIMEOUT_S
    for params in _params(llm):
        assert params['timeout'] == _DEFAULT_LLM_TIMEOUT_S


@pytest.mark.parametrize('value', [None, 0])
def test_explicit_opt_out_omits_timeout(value):
    llm = LLM(model='gpt-4o-mini', timeout=value)
    for params in _params(llm):
        assert 'timeout' not in params


def test_explicit_timeout_is_forwarded():
    llm = LLM(model='gpt-4o-mini', timeout=30)
    for params in _params(llm):
        assert params['timeout'] == 30
