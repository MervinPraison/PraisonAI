"""
Tests for litellm-free static capability fallback in model_capabilities.

When litellm is not installed, the ``supports_*`` helpers must fall back to a
conservative static heuristic instead of silently returning ``False`` for every
model (which would disable structured-output / tool-calling / caching / web
paths on lean installs and for newly released models).
"""

from types import SimpleNamespace
from unittest.mock import patch

from praisonaiagents.llm import model_capabilities as mc


def _no_litellm():
    """Force the litellm loader to report litellm as unavailable."""
    return patch.object(mc, "_get_litellm", return_value=None)


def _raising_litellm():
    """Force the loader to return an installed litellm whose helpers all raise."""
    def _raise(*args, **kwargs):
        raise RuntimeError("boom")

    fake = SimpleNamespace(
        supports_response_schema=_raise,
        supports_function_calling=_raise,
        supports_parallel_function_calling=_raise,
        supports_web_search=_raise,
        utils=SimpleNamespace(supports_prompt_caching=_raise),
    )
    return patch.object(mc, "_get_litellm", return_value=fake)


def _clear_caches():
    for fn in (
        mc.supports_structured_outputs,
        mc.supports_function_calling,
        mc.supports_parallel_function_calling,
        mc.supports_web_search,
        mc.supports_prompt_caching,
    ):
        fn.cache_clear()


def test_structured_outputs_fallback_without_litellm():
    _clear_caches()
    with _no_litellm():
        assert mc.supports_structured_outputs("gpt-4o") is True
        assert mc.supports_structured_outputs("openai/gpt-4o-mini") is True
        assert mc.supports_structured_outputs("claude-3-5-sonnet-latest") is True
        assert mc.supports_structured_outputs("some-unknown-model") is False
    _clear_caches()


def test_function_calling_fallback_without_litellm():
    _clear_caches()
    with _no_litellm():
        assert mc.supports_function_calling("gpt-4o") is True
        assert mc.supports_function_calling("anthropic/claude-3-5-sonnet-latest") is True
        assert mc.supports_function_calling("groq/llama-3.3-70b-versatile") is True
        # Non-chat models should not report tool calling
        assert mc.supports_function_calling("text-embedding-3-small") is False
        assert mc.supports_function_calling("whisper-1") is False
    _clear_caches()


def test_parallel_function_calling_fallback_without_litellm():
    _clear_caches()
    with _no_litellm():
        assert mc.supports_parallel_function_calling("gpt-4o") is True
        assert mc.supports_parallel_function_calling("text-embedding-3-small") is False
    _clear_caches()


def test_web_search_fallback_without_litellm():
    _clear_caches()
    with _no_litellm():
        assert mc.supports_web_search("openai/gpt-4o-search-preview") is True
        assert mc.supports_web_search("gemini-2.0-flash") is True
        assert mc.supports_web_search("perplexity/sonar") is True
        assert mc.supports_web_search("ollama/llama3") is False
    _clear_caches()


def test_prompt_caching_fallback_without_litellm():
    _clear_caches()
    with _no_litellm():
        assert mc.supports_prompt_caching("anthropic/claude-3-5-sonnet-latest") is True
        assert mc.supports_prompt_caching("gpt-4o") is True
        assert mc.supports_prompt_caching("deepseek/deepseek-chat") is True
        assert mc.supports_prompt_caching("ollama/llama3") is False
    _clear_caches()


def test_parallel_narrower_than_serial_without_litellm():
    # A serial-only tool-calling family (mistral) supports function calling but
    # must NOT be reported as supporting parallel tool calls by the heuristic.
    _clear_caches()
    with _no_litellm():
        assert mc.supports_function_calling("mistral/mistral-large-latest") is True
        assert mc.supports_parallel_function_calling("mistral/mistral-large-latest") is False
    _clear_caches()


def test_installed_litellm_error_stays_authoritative():
    # When litellm is installed but its helper raises, we must keep litellm
    # authoritative (return False) rather than overriding it with the static
    # heuristic — otherwise unsupported params could reach provider requests.
    _clear_caches()
    with _raising_litellm():
        assert mc.supports_structured_outputs("gpt-4o") is False
        assert mc.supports_function_calling("gpt-4o") is False
        assert mc.supports_parallel_function_calling("gpt-4o") is False
        assert mc.supports_web_search("gpt-4o-search-preview") is False
        assert mc.supports_prompt_caching("claude-3-5-sonnet-latest") is False
    _clear_caches()


def test_empty_model_name_is_false():
    _clear_caches()
    with _no_litellm():
        assert mc.supports_structured_outputs("") is False
        assert mc.supports_function_calling("") is False
        assert mc.supports_web_search("") is False
        assert mc.supports_prompt_caching("") is False
    _clear_caches()
