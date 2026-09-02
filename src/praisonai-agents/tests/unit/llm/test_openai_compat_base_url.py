"""
Tests for OpenAI-compatible routing of a bare model name + custom base_url.

A Chat Completions host (e.g. https://api.pzero.studio/v1) exposes catalog
model ids like ``deepseek-v4-flash`` with no ``provider/`` prefix. Without a
prefix LiteLLM cannot infer a provider and raises "LLM Provider NOT provided".
The LLM class should route such a bare model through the OpenAI-compatible
client by prefixing ``openai/`` at request-build time when a base_url is set.
"""

import pytest

from praisonaiagents.llm.llm import LLM


def test_bare_model_with_base_url_routes_openai():
    llm = LLM(
        model="deepseek-v4-flash",
        base_url="https://api.pzero.studio/v1",
        api_key="test-key",
    )
    params = llm._build_completion_params()
    assert params["model"] == "openai/deepseek-v4-flash"
    assert params["base_url"] == "https://api.pzero.studio/v1"
    assert params["api_key"] == "test-key"


def test_prefixed_model_with_base_url_unchanged():
    llm = LLM(
        model="openai/gpt-4o",
        base_url="https://custom.api.com/v1",
    )
    params = llm._build_completion_params()
    assert params["model"] == "openai/gpt-4o"


def test_bare_model_without_base_url_unchanged():
    llm = LLM(model="gpt-4o")
    params = llm._build_completion_params()
    assert params["model"] == "gpt-4o"


def test_anthropic_model_with_base_url_not_reprefixed():
    llm = LLM(
        model="claude-3-5-sonnet",
        base_url="https://proxy.example.com/v1",
    )
    params = llm._build_completion_params()
    assert params["model"] == "claude-3-5-sonnet"


def test_ollama_base_url_not_reprefixed():
    llm = LLM(
        model="llama3",
        base_url="http://localhost:11434",
    )
    params = llm._build_completion_params()
    assert params["model"] == "llama3"


def test_bare_model_with_subscription_base_url_routes_openai():
    """A subscription auth provider (e.g. qwen-cli/codex) injects an
    OpenAI-compatible base_url at request time. A bare model must still be
    routed through ``openai/`` even though the instance ``base_url`` is empty.
    """
    from praisonaiagents.auth.subscription.protocols import SubscriptionCredentials

    llm = LLM(model="qwen3-coder-plus")
    llm._auth_provider_id = "qwen-cli"
    llm._cached_subscription_creds = SubscriptionCredentials(
        api_key="test-token",
        base_url="https://portal.qwen.ai/v1",
    )
    params = llm._build_completion_params()
    assert params["model"] == "openai/qwen3-coder-plus"
    assert params["base_url"] == "https://portal.qwen.ai/v1"


def test_bare_model_no_subscription_base_url_unchanged():
    """Subscription creds without a base_url must not trigger prefixing."""
    from praisonaiagents.auth.subscription.protocols import SubscriptionCredentials

    llm = LLM(model="gpt-4o")
    llm._auth_provider_id = "some-provider"
    llm._cached_subscription_creds = SubscriptionCredentials(api_key="test-token")
    params = llm._build_completion_params()
    assert params["model"] == "gpt-4o"
