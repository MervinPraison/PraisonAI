"""Model price matching for the CLI cost tracker (Issue #6043)."""

import os
import sys
import types

os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "True")

import pytest

from praisonai_code.cli.features import cost_tracker
from praisonai_code.cli.features.cost_tracker import DEFAULT_PRICING, get_pricing


@pytest.fixture
def no_litellm(monkeypatch):
    """Exercise the static-table fallback only."""
    monkeypatch.setattr(cost_tracker, "_litellm_pricing", lambda _name: None)


def test_exact_names_keep_static_prices():
    for name in ("gpt-4o", "gpt-4o-mini", "gpt-4", "claude-3-haiku"):
        assert get_pricing(name) is DEFAULT_PRICING[name]


def test_provider_prefix_matches_bare_name():
    assert get_pricing("openai/gpt-4o-mini") is get_pricing("gpt-4o-mini")


def test_longer_model_never_matches_shorter_key(no_litellm):
    assert get_pricing("gpt-4.1-mini").model_name != "gpt-4"
    assert get_pricing("gpt-4.1").model_name != "gpt-4"


def test_longest_prefix_key_wins(no_litellm):
    assert get_pricing("gpt-4o-mini-2024-07-18") is DEFAULT_PRICING["gpt-4o-mini"]
    assert get_pricing("openai/gpt-4o-2024-08-06") is DEFAULT_PRICING["gpt-4o"]


def test_litellm_price_map_used_for_models_missing_from_table(monkeypatch):
    fake = types.SimpleNamespace(model_cost={
        "gpt-4.1-mini": {
            "input_cost_per_token": 4e-07,
            "output_cost_per_token": 1.6e-06,
            "max_input_tokens": 1047576,
        },
    })
    monkeypatch.setitem(sys.modules, "litellm", fake)

    pricing = get_pricing("openai/gpt-4.1-mini")
    assert pricing.priced
    assert pricing.input_price_per_1m == 0.4
    assert pricing.output_price_per_1m == 1.6
    assert pricing.context_window == 1047576


def test_unknown_model_is_flagged_unpriced(no_litellm):
    pricing = get_pricing("my-local-model")
    assert pricing is DEFAULT_PRICING["default"]
    assert pricing.priced is False
    assert get_pricing("").priced is False


def test_collected_usage_cost_is_none_for_unknown_model(monkeypatch, no_litellm):
    from praisonaiagents.telemetry.token_collector import TokenMetrics, get_token_collector

    collector = get_token_collector()
    collector.reset()
    try:
        collector.track_tokens("my-local-model", "a", TokenMetrics(input_tokens=10, output_tokens=5))
        usage = cost_tracker.price_collected_usage("my-local-model")
        assert usage == {"in": 10, "out": 5, "cost": None}
    finally:
        collector.reset()
