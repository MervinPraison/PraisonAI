"""Deterministic request/programming errors must not replay provider calls."""
import asyncio
from unittest.mock import AsyncMock, Mock, patch

import litellm
import pytest

from praisonaiagents.llm import LLM
from praisonaiagents.llm.llm import LLMResponseError


def make_llm():
    return LLM(
        model="openai/gpt-4o-mini",
        api_key="synthetic-offline-fixture",
        base_url="http://127.0.0.1:1/v1",
        max_retries=1,
    )


@pytest.mark.parametrize("message", [
    "Invalid value: max_tokens=5000 exceeds limit 4096",
    "n must be <= 128, got 1500",
    "user id 6429 not permitted",
])
def test_public_response_call_does_not_retry_bad_request(message):
    error = litellm.BadRequestError(
        message, model="gpt-4o-mini", llm_provider="openai"
    )
    boundary = Mock(side_effect=error)
    llm = make_llm()
    with patch("litellm.responses", boundary), patch("time.sleep") as sleep:
        with pytest.raises(LLMResponseError):
            llm.get_response(prompt="Hello", stream=False)
    assert boundary.call_count == 1
    sleep.assert_not_called()
    assert llm.classify_error_kind(error) == "format_error"


def test_async_public_response_call_does_not_retry_bad_request():
    error = litellm.BadRequestError(
        "Invalid value: max_tokens=5000 exceeds limit 4096",
        model="gpt-4o-mini", llm_provider="openai",
    )
    boundary = AsyncMock(side_effect=error)
    llm = make_llm()
    with patch("litellm.aresponses", boundary), patch("asyncio.sleep") as sleep:
        with pytest.raises(litellm.BadRequestError):
            asyncio.run(llm.get_response_async(prompt="Hello", stream=False))
    assert boundary.await_count == 1
    sleep.assert_not_called()


@pytest.mark.parametrize("error", [
    ValueError("invalid setting"), TypeError("invalid call"), KeyError("missing")
])
def test_programming_error_is_not_retryable(error):
    llm = make_llm()
    boundary = Mock(side_effect=error)
    with patch("litellm.responses", boundary), patch("time.sleep") as sleep:
        with pytest.raises(LLMResponseError):
            llm.get_response(prompt="Hello", stream=False)
    assert boundary.call_count == 1
    sleep.assert_not_called()


@pytest.mark.parametrize("error_type, message, expected", [
    (litellm.RateLimitError, "rate limited", "rate_limit"),
    (litellm.ServiceUnavailableError, "service unavailable", "overloaded"),
    (litellm.BadRequestError, "context length exceeded", "context_overflow"),
    (litellm.RateLimitError, "insufficient quota", "billing"),
])
def test_existing_provider_recovery_categories_remain(error_type, message, expected):
    error = error_type(message, llm_provider="openai", model="gpt-4o-mini")
    assert make_llm().classify_error_kind(error) == expected


def test_message_status_fallback_does_not_match_embedded_digits():
    llm = make_llm()
    error = Exception("max_tokens=5000 exceeds limit")
    assert llm.classify_error_kind(error) == "unknown"
    assert llm.classify_error_kind(Exception("HTTP 503 service failure")) == "overloaded"
