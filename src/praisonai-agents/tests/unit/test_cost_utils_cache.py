"""Cache-aware and provider-reported cost accounting (issue #5995)."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from praisonaiagents.utils.cost_utils import calculate_llm_cost


def test_no_cache_data_keeps_flat_pricing():
    # 1M in @ 0.15 + 1M out @ 0.60
    assert calculate_llm_cost(1_000_000, 1_000_000, "gpt-4o-mini") == pytest.approx(0.75)


def test_cached_tokens_priced_at_cache_read_rate():
    # 1M prompt of which 800k cached at 50%: (200k + 400k) * 2.50/1M
    cost = calculate_llm_cost(1_000_000, 0, "gpt-4o", cached_tokens=800_000)
    assert cost == pytest.approx(1.5)


def test_cached_tokens_read_from_openai_style_response():
    usage = SimpleNamespace(
        prompt_tokens=1_000_000,
        completion_tokens=0,
        prompt_tokens_details=SimpleNamespace(cached_tokens=1_000_000),
    )
    cost = calculate_llm_cost(1_000_000, 0, "gpt-4o", response=SimpleNamespace(usage=usage))
    assert cost == pytest.approx(1.25)


def test_anthropic_cache_read_and_write_from_dict_response():
    response = {
        "usage": {
            "prompt_tokens": 1_000_000,
            "cache_read_input_tokens": 500_000,
            "cache_creation_input_tokens": 100_000,
        }
    }
    # 400k * 1 + 500k * 0.1 + 100k * 1.25 = 575k tokens @ 3.00/1M
    cost = calculate_llm_cost(1_000_000, 0, "claude-3-5-sonnet-20241022", response=response)
    assert cost == pytest.approx(1.725)


def test_cached_tokens_clamped_to_prompt_tokens():
    assert calculate_llm_cost(100, 0, "gpt-4o", cached_tokens=10_000) == pytest.approx(
        calculate_llm_cost(100, 0, "gpt-4o", cached_tokens=100)
    )


def test_unknown_model_cache_defaults_to_input_rate():
    assert calculate_llm_cost(1_000_000, 0, "some-model", cached_tokens=500_000) == pytest.approx(1.0)


def test_provider_reported_cost_is_authoritative():
    usage = SimpleNamespace(prompt_tokens=1_000_000, completion_tokens=1_000_000, cost=0.0123)
    cost = calculate_llm_cost(1_000_000, 1_000_000, "gpt-4o", response=SimpleNamespace(usage=usage))
    assert cost == pytest.approx(0.0123)


def test_reported_zero_cost_wins():
    response = SimpleNamespace(usage=None, _hidden_params={"response_cost": 0.0})
    assert calculate_llm_cost(1_000_000, 1_000_000, "gpt-4o", response=response) == 0.0


def test_mock_response_does_not_leak_into_cost():
    assert calculate_llm_cost(1_000_000, 0, "gpt-4o-mini", response=MagicMock()) == pytest.approx(0.15)


def test_agent_accounting_uses_cached_tokens():
    from praisonaiagents import Agent

    agent = Agent(name="t", instructions="x", llm="gpt-4o")
    usage = SimpleNamespace(
        prompt_tokens=1_000_000,
        completion_tokens=0,
        prompt_tokens_details=SimpleNamespace(cached_tokens=1_000_000),
    )
    response = SimpleNamespace(usage=usage)
    assert agent._calculate_llm_cost(1_000_000, 0, response=response) == pytest.approx(1.25)
