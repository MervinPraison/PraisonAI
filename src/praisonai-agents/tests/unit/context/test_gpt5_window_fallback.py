import pytest

from praisonaiagents.context import budgeter
from praisonaiagents.eval.tokens import get_context_length


@pytest.mark.parametrize('model', ['gpt-5', 'gpt-5-mini', 'gpt-5-nano', 'gpt-5-2025-08-07'])
def test_offline_gpt5_full_window_and_meter(monkeypatch, model):
    monkeypatch.setattr(budgeter, '_litellm_model_info', lambda _: None)
    assert budgeter.get_model_limit(model) == 400000
    assert budgeter.context_window_usage(200000, model) == {'used': 200000, 'limit': 400000, 'percent': 50}
    assert budgeter.ContextBudgeter(model=model).model_limit == 400000
    assert get_context_length(model) == 400000


def test_litellm_input_limit_keeps_existing_precedence(monkeypatch):
    monkeypatch.setattr(budgeter, '_litellm_model_info', lambda _: {'max_input_tokens': 272000})
    assert budgeter.get_model_limit('gpt-5') == 272000


@pytest.mark.parametrize('model,expected', [
    ('gpt-5.4', 1050000), ('gpt-5.4-pro', 1050000),
    ('gpt-5.4-mini', 400000), ('gpt-5.4-nano', 400000),
    ('gpt-5.4-mini-2026-03-17', 400000),
    ('openai/gpt-5.4-2026-03-05', 1050000),
])
def test_newer_specific_model_is_not_shadowed_by_gpt5_prefix(monkeypatch, model, expected):
    monkeypatch.setattr(budgeter, '_litellm_model_info', lambda _: None)
    assert budgeter.get_model_limit(model) == expected
