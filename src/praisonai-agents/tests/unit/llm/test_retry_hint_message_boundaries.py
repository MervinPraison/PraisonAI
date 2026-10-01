"""Retry hints must distinguish punctuation from malformed field contents."""

import pytest

from praisonaiagents.llm.error_classifier import extract_retry_after
from praisonaiagents.llm.llm import LLM


@pytest.mark.parametrize('token,expected', [('0.5.', .5), ('1e-1.', .1), ('.5.', .5)])
@pytest.mark.parametrize('prefix', ['try again in ', 'retry after ', 'wait '])
def test_sentence_period_keeps_fractional_hint(token, expected, prefix):
    error = Exception('rate limit: ' + prefix + token)
    assert extract_retry_after(error) == expected
    decision = LLM(model='fake').resolve_failover_decision(
        error, {'attempt': 1, 'max_retries': 3, 'side_effecting': False},
    )
    assert decision.backoff_ms == int(expected * 1000)


@pytest.mark.parametrize('key', ['"retryDelay"', 'retryDelay'])
@pytest.mark.parametrize('value', ['"5s more"', '"5sfoo"', '"5s'])
def test_incomplete_quoted_field_does_not_hide_valid_hint(key, value):
    message = f'rate limit: {key}: {value}, retry after 20 seconds'
    assert extract_retry_after(Exception(message)) == 20
    assert LLM(model='fake')._parse_retry_delay(message) == 20


@pytest.mark.parametrize('message', [
    'retryDelay: 5s', 'retryDelay: "5s"', '"retryDelay": "5s"',
])
def test_complete_duration_field_is_preserved(message):
    assert extract_retry_after(Exception(message)) == 5


@pytest.mark.parametrize('token', ['1.2.3', '1e-1.2', '0.5..'])
def test_embedded_period_remains_invalid(token):
    assert extract_retry_after(Exception('try again in ' + token)) is None
