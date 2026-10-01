"""Invalid provider retry hints must not produce invalid delays or holds."""

import math

import pytest

from praisonaiagents.llm.error_classifier import classify_llm_error, extract_retry_after


@pytest.mark.parametrize("value", ["nan", "inf", "-inf", "-1"])
def test_invalid_header_is_ignored(value):
    error = Exception("rate limited")
    error.headers = {"retry-after": value}
    assert extract_retry_after(error) is None


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -float("inf"), -1.0])
def test_invalid_attribute_is_ignored(value):
    error = Exception("rate limited")
    error.retry_after = value
    assert extract_retry_after(error) is None


def test_invalid_header_falls_through_to_valid_attribute():
    error = Exception("rate limited")
    error.headers = {"retry-after": "nan"}
    error.retry_after = 7
    assert extract_retry_after(error) == 7


def test_invalid_attribute_falls_through_to_valid_message():
    error = Exception("rate limited; retry after 12 seconds")
    error.retry_after = float("nan")
    assert extract_retry_after(error) == 12


def test_nan_hint_does_not_poison_classified_backoff():
    error = Exception("rate limited")
    error.headers = {"retry-after": "nan"}
    result = classify_llm_error(error, provider="openai", model="gpt-4o-mini")
    assert math.isfinite(result.backoff_seconds)
    assert result.backoff_seconds >= 0


def test_nan_hint_does_not_poison_scheduler_hold():
    from praisonaiagents.scheduler.due import quota_hold_from_failure

    error = Exception("rate limited")
    error.headers = {"retry-after": "nan"}
    assert quota_hold_from_failure(error, now=1000) is None


@pytest.mark.parametrize("value", ["0", "0.5", "9999"])
def test_valid_header_keeps_zero_fraction_and_cap(value):
    error = Exception("rate limited")
    error.headers = {"retry-after": value}
    assert extract_retry_after(error) == min(float(value), 300)
