"""Tests for ContextAggregator token-budget truncation."""

import asyncio

from praisonaiagents.context.aggregator import ContextAggregator


def _run(coro):
    return asyncio.run(coro)


def test_ascii_truncation_within_budget():
    aggregator = ContextAggregator(max_tokens=200, include_source_labels=False)
    long_text = "word " * 2000
    aggregator.register_source("src", lambda q: long_text)

    result = _run(aggregator.aggregate("query"))

    assert aggregator._estimate_tokens(result.context) <= 200


def test_non_ascii_truncation_within_budget():
    # CJK characters are weighted ~1.3 tokens/char by the canonical heuristic,
    # so the old `remaining * 4` char estimate massively over-retained.
    aggregator = ContextAggregator(max_tokens=200, include_source_labels=False)
    cjk_text = "\u4f60\u597d\u4e16\u754c" * 500
    aggregator.register_source("src", lambda q: cjk_text)

    result = _run(aggregator.aggregate("query"))

    assert aggregator._estimate_tokens(result.context) <= 200


def test_non_ascii_truncation_within_budget_with_labels():
    aggregator = ContextAggregator(max_tokens=200, include_source_labels=True)
    cjk_text = "\u4f60\u597d\u4e16\u754c" * 500
    aggregator.register_source("memory", lambda q: cjk_text)

    result = _run(aggregator.aggregate("query"))

    assert aggregator._estimate_tokens(result.context) <= 200


def test_truncate_to_tokens_helper():
    aggregator = ContextAggregator()
    cjk_text = "\u4f60\u597d" * 100

    truncated = aggregator._truncate_to_tokens(cjk_text, 50)

    assert aggregator._estimate_tokens(truncated) <= 50
    assert truncated == cjk_text[: len(truncated)]


def test_truncate_to_tokens_returns_full_when_fits():
    aggregator = ContextAggregator()
    text = "hello world"

    assert aggregator._truncate_to_tokens(text, 1000) == text


def test_truncate_to_tokens_empty_and_zero_budget():
    aggregator = ContextAggregator()

    assert aggregator._truncate_to_tokens("", 100) == ""
    assert aggregator._truncate_to_tokens("hello", 0) == ""
