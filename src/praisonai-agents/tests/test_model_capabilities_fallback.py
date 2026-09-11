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


# ---------------------------------------------------------------------------
# max_output_tokens — CLI output-budget ceiling accessor
# ---------------------------------------------------------------------------


def _litellm_with(get_info=None, model_cost=None):
    """Return a fake litellm exposing get_model_info / model_cost."""
    ns = SimpleNamespace()
    if get_info is not None:
        ns.get_model_info = get_info
    if model_cost is not None:
        ns.model_cost = model_cost
    return patch.object(mc, "_get_litellm", return_value=ns)


def test_max_output_tokens_none_without_litellm():
    mc.max_output_tokens.cache_clear()
    with _no_litellm():
        assert mc.max_output_tokens("gpt-4o") is None
    mc.max_output_tokens.cache_clear()


def test_max_output_tokens_empty_name_is_none():
    mc.max_output_tokens.cache_clear()
    assert mc.max_output_tokens("") is None
    mc.max_output_tokens.cache_clear()


def test_max_output_tokens_from_get_model_info():
    mc.max_output_tokens.cache_clear()

    def _info(model):
        return {"max_output_tokens": 4096, "max_tokens": 128000}

    with _litellm_with(get_info=_info):
        assert mc.max_output_tokens("gpt-4o") == 4096
    mc.max_output_tokens.cache_clear()


def test_max_output_tokens_ignores_context_only_max_tokens():
    # Regression: ``max_tokens`` is a context-window field here. When output
    # metadata is absent, the accessor must NOT substitute it (that would leak
    # a 128k context as a 128k output ceiling and defeat the clamp).
    mc.max_output_tokens.cache_clear()

    def _info(model):
        return {"max_tokens": 128000}  # no max_output_tokens

    with _litellm_with(get_info=_info, model_cost={}):
        assert mc.max_output_tokens("some-model") is None
    mc.max_output_tokens.cache_clear()


def test_max_output_tokens_model_cost_fallback():
    mc.max_output_tokens.cache_clear()

    def _raise(model):
        raise RuntimeError("get_model_info miss")

    cost = {"claude-3-5-sonnet-latest": {"max_output_tokens": 8192}}
    with _litellm_with(get_info=_raise, model_cost=cost):
        assert mc.max_output_tokens("claude-3-5-sonnet-latest") == 8192
        # Provider-prefixed name resolves via the strip-prefix branch.
        assert mc.max_output_tokens("anthropic/claude-3-5-sonnet-latest") == 8192
    mc.max_output_tokens.cache_clear()


def test_max_output_tokens_unknown_model_is_none():
    mc.max_output_tokens.cache_clear()

    def _raise(model):
        raise RuntimeError("miss")

    with _litellm_with(get_info=_raise, model_cost={}):
        assert mc.max_output_tokens("totally-unknown-model") is None
    mc.max_output_tokens.cache_clear()
