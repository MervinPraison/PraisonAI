"""Current models are priced at their list price, not the $1/$3 default.

Expected figures are worked out by hand from the provider pricing pages
(USD per 1M tokens), not read back from the price table under test:

- OpenAI (developers.openai.com/api/docs/pricing): gpt-5.5 $5 in, $0.50
  cached in, $30 out; gpt-4.1 $2 in, $8 out; gpt-4o-2024-05-13 $5 in, $15 out.
- Anthropic (platform.claude.com/docs/en/about-claude/pricing): Opus 4.6 $5
  in, $6.25 5-minute cache write, $0.50 cache hit, $25 out; Sonnet 4.6 $3,
  $3.75, $0.30, $15.
"""

from types import SimpleNamespace

import pytest

from praisonaiagents.utils.cost_utils import calculate_llm_cost


@pytest.mark.parametrize(
    "model, expected",
    [
        # 100k in + 5k out
        ("gpt-5.5", (100_000 * 5 + 5_000 * 30) / 1e6),
        ("claude-opus-4-6", (100_000 * 5 + 5_000 * 25) / 1e6),
        ("claude-sonnet-4-6", (100_000 * 3 + 5_000 * 15) / 1e6),
        # "gpt-4.1" does not match the "gpt-4" key and fell to the default
        ("gpt-4.1", (100_000 * 2 + 5_000 * 8) / 1e6),
        # the dated snapshot has its own (higher) price than gpt-4o
        ("gpt-4o-2024-05-13", (100_000 * 5 + 5_000 * 15) / 1e6),
    ],
)
def test_current_models_use_list_price(model, expected):
    assert calculate_llm_cost(100_000, 5_000, model) == pytest.approx(expected)


def test_openai_cached_tokens_use_cache_read_price():
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
def test_anthropic_cache_reads_and_writes(model, rates):
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


def test_cache_write_without_a_write_price_bills_as_input():
    # OpenAI lists no separate cache-write price
    assert calculate_llm_cost(
        100_000, 0, "gpt-5.5", cache_write_tokens=40_000
    ) == pytest.approx(100_000 * 5 / 1e6)


def test_unlisted_models_keep_the_fallback_table():
    # retired ids and local models are not in llm-prices
    assert calculate_llm_cost(1_000_000, 0, "claude-3-5-sonnet-20241022") == pytest.approx(3.0)
    assert calculate_llm_cost(1_000_000, 1_000_000, "ollama/llama3") == pytest.approx(4.0)


def test_agent_budget_sees_list_price():
    from praisonaiagents import Agent

    agent = Agent(name="b", instructions="x", llm="claude-opus-4-6")
    response = SimpleNamespace(
        usage=SimpleNamespace(prompt_tokens=100_000, completion_tokens=5_000)
    )
    assert agent._calculate_llm_cost(100_000, 5_000, response=response) == pytest.approx(0.625)
