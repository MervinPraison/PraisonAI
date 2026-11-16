"""Current models are priced at their list price, not the $1/$3 default.

Expected figures are worked out by hand from the provider pricing pages
(USD per 1M tokens), not read back from the price table under test:

- OpenAI: gpt-5.5 $5 in, $0.50 cached in, $30 out; gpt-5.5-pro $30/$180;
  gpt-5-mini $0.25/$2; gpt-4.1 $2/$8; o3 $2/$8.
- Anthropic: Opus 4.5+ $5 in, $6.25 5-minute cache write, $0.50 cache hit,
  $25 out; Opus 4.1 $15/$75; Sonnet 4.x $3, $3.75, $0.30, $15; Haiku 4.5 $1/$5.
- Google: gemini-2.5-pro $1.25/$10.

No network and no extra package: the table is in cost_utils, and litellm's
``model_cost`` is used only when litellm is already imported (faked here).
"""

import sys
from types import SimpleNamespace

import pytest

from praisonaiagents.utils.cost_utils import calculate_llm_cost


@pytest.fixture
def no_litellm(monkeypatch):
    monkeypatch.delitem(sys.modules, "litellm", raising=False)


@pytest.mark.parametrize(
    "model, expected",
    [
        # 100k in + 5k out
        ("gpt-5.5", (100_000 * 5 + 5_000 * 30) / 1e6),
        ("gpt-5.5-pro", (100_000 * 30 + 5_000 * 180) / 1e6),
        ("gpt-5-mini", (100_000 * 0.25 + 5_000 * 2) / 1e6),
        ("o3", (100_000 * 2 + 5_000 * 8) / 1e6),
        ("claude-opus-4-6", (100_000 * 5 + 5_000 * 25) / 1e6),
        ("claude-opus-4-1-20250805", (100_000 * 15 + 5_000 * 75) / 1e6),
        ("claude-sonnet-4-6", (100_000 * 3 + 5_000 * 15) / 1e6),
        ("anthropic/claude-sonnet-4-5-20250929", (100_000 * 3 + 5_000 * 15) / 1e6),
        ("claude-haiku-4-5", (100_000 * 1 + 5_000 * 5) / 1e6),
        ("gemini/gemini-2.5-pro", (100_000 * 1.25 + 5_000 * 10) / 1e6),
        # "gpt-4.1" does not match the "gpt-4" key and fell to the default
        ("gpt-4.1", (100_000 * 2 + 5_000 * 8) / 1e6),
    ],
)
def test_current_models_use_list_price(no_litellm, model, expected):
    assert calculate_llm_cost(100_000, 5_000, model) == pytest.approx(expected)


@pytest.mark.parametrize(
    "model, expected",
    [("gpt-4o-mini", 0.75), ("gpt-4o", 12.5), ("claude-3-5-sonnet-20241022", 18.0)],
)
def test_models_priced_before_are_unchanged(no_litellm, model, expected):
    assert calculate_llm_cost(1_000_000, 1_000_000, model) == pytest.approx(expected)


def test_openai_cached_tokens_use_cache_read_price(no_litellm):
    # 100k prompt, 60k of it cached; 5k out
    expected = (40_000 * 5 + 60_000 * 0.50 + 5_000 * 30) / 1e6
    cost = calculate_llm_cost(100_000, 5_000, "openai/gpt-5.5", cached_tokens=60_000)
    assert cost == pytest.approx(expected)


@pytest.mark.parametrize(
    "model, rates",
    [
        # (input, cache write 5m, cache read, output)
        ("claude-opus-4-6", (5, 6.25, 0.50, 25)),
        ("anthropic/claude-sonnet-4-6", (3, 3.75, 0.30, 15)),
    ],
)
def test_anthropic_cache_reads_and_writes(no_litellm, model, rates):
    inp, write, read, out = rates
    response = {
        "usage": {
            "prompt_tokens": 100_000,
            "completion_tokens": 5_000,
            "cache_read_input_tokens": 50_000,
            "cache_creation_input_tokens": 20_000,
        }
    }
    expected = (30_000 * inp + 20_000 * write + 50_000 * read + 5_000 * out) / 1e6
    assert calculate_llm_cost(100_000, 5_000, model, response=response) == pytest.approx(expected)


def test_cache_write_without_a_write_price_bills_as_input(no_litellm):
    # OpenAI lists no separate cache-write price for gpt-5.5
    assert calculate_llm_cost(
        100_000, 0, "gpt-5.5", cache_write_tokens=40_000
    ) == pytest.approx(100_000 * 5 / 1e6)


def test_unknown_model_uses_loaded_litellm_table(monkeypatch):
    fake = SimpleNamespace(model_cost={
        "mistral/mistral-large-latest": {
            "input_cost_per_token": 2e-6,
            "output_cost_per_token": 6e-6,
            "cache_read_input_token_cost": 2e-7,
        },
        "ollama/llama3": {"input_cost_per_token": 0.0, "output_cost_per_token": 0.0},
    })
    monkeypatch.setitem(sys.modules, "litellm", fake)
    assert calculate_llm_cost(
        1_000_000, 1_000_000, "mistral/mistral-large-latest", cached_tokens=500_000
    ) == pytest.approx(0.5 * 2 + 0.5 * 0.2 + 6)
    # zero-priced (local) entries keep the conservative default
    assert calculate_llm_cost(1_000_000, 1_000_000, "ollama/llama3") == pytest.approx(4.0)
    # the table still wins over litellm for models it lists
    fake.model_cost["gpt-4o-mini"] = {"input_cost_per_token": 1.0, "output_cost_per_token": 1.0}
    assert calculate_llm_cost(1_000_000, 1_000_000, "gpt-4o-mini") == pytest.approx(0.75)


def test_unknown_model_never_imports_litellm(no_litellm):
    assert calculate_llm_cost(1_000_000, 1_000_000, "mistral/mistral-large-latest") == pytest.approx(4.0)
    assert "litellm" not in sys.modules


def test_agent_budget_sees_list_price(no_litellm):
    from praisonaiagents import Agent

    agent = Agent(name="b", instructions="x", llm="claude-opus-4-6")
    response = SimpleNamespace(
        usage=SimpleNamespace(prompt_tokens=100_000, completion_tokens=5_000)
    )
    assert agent._calculate_llm_cost(100_000, 5_000, response=response) == pytest.approx(0.625)
