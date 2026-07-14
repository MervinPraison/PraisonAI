"""
Regression tests for issue #3010: the LLM provider registry must be visible
from the wrapper's hot LLM paths (``PraisonAIModel`` and ``AutoGenerator``).

A provider registered via ``register_llm_provider`` should take effect through
both hot paths, while built-in providers and unregistered providers keep their
existing behaviour unchanged.
"""

import asyncio
import os

import pytest


@pytest.fixture(autouse=True)
def _reset_registry():
    """Reset the default LLM registry before/after each test for isolation."""
    from praisonai.llm import _reset_default_registry
    _reset_default_registry()
    yield
    _reset_default_registry()


# ---------------------------------------------------------------------------
# PraisonAIModel.get_model()
# ---------------------------------------------------------------------------

def test_registered_provider_resolved_by_praisonai_model(monkeypatch):
    """A registered non-built-in provider is resolved via the registry."""
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    from praisonai.llm import register_llm_provider
    from praisonai.inc.models import PraisonAIModel

    class BedrockProvider:
        provider_id = "bedrock"

        def __init__(self, model_id, config=None):
            self.model_id = model_id
            self.config = config or {}

        def get_client(self):
            return ("bedrock-client", self.model_id)

    register_llm_provider("bedrock", BedrockProvider, override=True)

    model = PraisonAIModel(model="bedrock/anthropic.claude-3-sonnet")
    client = model.get_model()
    assert client == ("bedrock-client", "anthropic.claude-3-sonnet")


def test_registered_provider_without_get_client_returned_as_is(monkeypatch):
    """Providers lacking get_client are returned directly."""
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    from praisonai.llm import register_llm_provider
    from praisonai.inc.models import PraisonAIModel

    sentinel = object()

    class NoClientProvider:
        provider_id = "custprov"

        def __init__(self, model_id, config=None):
            self.model_id = model_id

        # Instances need provider_id + model_id so create_llm_provider passes
        # them through unchanged; return the instance itself as the "client".

    register_llm_provider("custprov", NoClientProvider, override=True)
    model = PraisonAIModel(model="custprov/whatever")
    client = model.get_model()
    assert isinstance(client, NoClientProvider)


def test_builtin_prefix_not_delegated_to_registry(monkeypatch):
    """Built-in prefixes keep their direct-SDK resolution (no registry)."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    from praisonai.inc.models import PraisonAIModel

    model = PraisonAIModel(model="openai/gpt-4o-mini")
    assert model.api_key_var == "OPENAI_API_KEY"
    assert model.base_url == "https://api.openai.com/v1"
    assert model._resolve_registered_provider() is None


def test_registered_provider_construction_failure_is_surfaced(monkeypatch):
    """A broken registered provider surfaces its error, not a masked OpenAI 401."""
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    from praisonai.llm import register_llm_provider
    from praisonai.inc.models import PraisonAIModel

    class BrokenProvider:
        provider_id = "brokenprov"

        def __init__(self, model_id, config=None):
            raise RuntimeError("provider boom")

    register_llm_provider("brokenprov", BrokenProvider, override=True)

    model = PraisonAIModel(model="brokenprov/x")
    with pytest.raises(RuntimeError, match="provider boom"):
        model.get_model()


def test_registered_provider_receives_no_none_api_key(monkeypatch):
    """No OpenAI key => registered provider config omits api_key entirely."""
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    from praisonai.llm import register_llm_provider
    from praisonai.inc.models import PraisonAIModel

    seen = {}

    class ConfigCaptureProvider:
        provider_id = "capprov"

        def __init__(self, model_id, config=None):
            self.model_id = model_id
            self.config = config
            seen["config"] = config

        def get_client(self):
            return "ok"

    register_llm_provider("capprov", ConfigCaptureProvider, override=True)
    model = PraisonAIModel(model="capprov/m")
    model.get_model()
    # api_key must NOT be present as None so the provider uses its own chain.
    cfg = seen["config"] or {}
    assert "api_key" not in cfg or cfg["api_key"]


def test_unregistered_unknown_provider_still_requires_openai_key(monkeypatch):
    """Unknown, unregistered providers keep the historical OpenAI-key error."""
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_BASE", raising=False)
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    from praisonai.inc.models import PraisonAIModel

    with pytest.raises(ValueError):
        PraisonAIModel(model="totallyunknown/foo")


# ---------------------------------------------------------------------------
# AutoGenerator._completion_impl
# ---------------------------------------------------------------------------

def test_auto_generator_uses_registered_provider(monkeypatch):
    """A registered provider exposing generate_structured serves completions."""
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    from praisonai.llm import register_llm_provider
    from praisonai.auto import BaseAutoGenerator

    class Result:
        def __init__(self, answer):
            self.answer = answer

    class MyProvider:
        provider_id = "myprov"

        def __init__(self, model_id, config=None):
            self.model_id = model_id

        async def generate_structured(self, response_model, messages, **kwargs):
            return response_model("from-registered-provider")

    register_llm_provider("myprov", MyProvider, override=True)

    gen = BaseAutoGenerator(config_list=[{"model": "myprov/some-model"}])
    out = asyncio.run(
        gen._completion_impl(Result, [{"role": "user", "content": "hi"}], is_async=True)
    )
    assert out.answer == "from-registered-provider"


def test_auto_generator_opt_out_without_generate_structured(monkeypatch):
    """Registered providers without generate_structured fall back to the ladder."""
    from praisonai.llm import register_llm_provider
    from praisonai.auto import BaseAutoGenerator

    class NoStruct:
        provider_id = "nostruct"

        def __init__(self, model_id, config=None):
            self.model_id = model_id

    register_llm_provider("nostruct", NoStruct, override=True)
    gen = BaseAutoGenerator(config_list=[{"model": "nostruct/x"}])
    result = asyncio.run(
        gen._structured_via_registered_provider(object, [], "nostruct/x")
    )
    assert result is None


def test_auto_generator_unregistered_provider_falls_through():
    """Unregistered providers return None so the built-in ladder runs."""
    from praisonai.auto import BaseAutoGenerator

    gen = BaseAutoGenerator(config_list=[{"model": "totallyunknown/x"}])
    result = asyncio.run(
        gen._structured_via_registered_provider(object, [], "totallyunknown/x")
    )
    assert result is None


def test_auto_generator_builtin_prefix_not_delegated(monkeypatch):
    """A custom provider registered under a built-in prefix must NOT hijack the
    AutoGenerator built-in path — mirrors PraisonAIModel so both hot paths agree.
    """
    from praisonai.llm import register_llm_provider
    from praisonai.auto import BaseAutoGenerator

    class HijackProvider:
        provider_id = "openai"

        def __init__(self, model_id, config=None):
            self.model_id = model_id

        async def generate_structured(self, response_model, messages, **kwargs):
            raise AssertionError("built-in prefix must not use the registry")

    register_llm_provider("openai", HijackProvider, override=True)
    gen = BaseAutoGenerator(config_list=[{"model": "openai/gpt-4o-mini"}])
    result = asyncio.run(
        gen._structured_via_registered_provider(object, [], "openai/gpt-4o-mini")
    )
    assert result is None


def test_auto_generator_preserves_provider_specific_config(monkeypatch):
    """Provider-specific config fields are forwarded; empty credentials dropped."""
    from praisonai.llm import register_llm_provider
    from praisonai.auto import BaseAutoGenerator

    seen = {}

    class Result:
        def __init__(self, answer):
            self.answer = answer

    class CfgProvider:
        provider_id = "cfgprov"

        def __init__(self, model_id, config=None):
            self.model_id = model_id
            seen["config"] = config

        async def generate_structured(self, response_model, messages, **kwargs):
            return response_model("ok")

    register_llm_provider("cfgprov", CfgProvider, override=True)
    gen = BaseAutoGenerator(
        config_list=[{
            "model": "cfgprov/m",
            "aws_region": "us-east-1",
            "timeout": 42,
            "api_key": "",
            "base_url": "",
        }]
    )
    out = asyncio.run(
        gen._completion_impl(Result, [{"role": "user", "content": "hi"}], is_async=True)
    )
    assert out.answer == "ok"
    cfg = seen["config"] or {}
    # Provider-specific fields preserved.
    assert cfg.get("aws_region") == "us-east-1"
    assert cfg.get("timeout") == 42
    # Empty credential fields dropped, and "model" is never forwarded.
    assert "api_key" not in cfg
    assert "base_url" not in cfg
    assert "model" not in cfg
