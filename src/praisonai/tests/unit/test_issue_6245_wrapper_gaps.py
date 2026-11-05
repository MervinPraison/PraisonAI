"""Regression tests for #6245: no silent OpenAI misroute, no silent safety drop."""
import pytest

from praisonai.framework_adapters.base import warn_unsupported_fields
from praisonai.inc.models import PraisonAIModel


@pytest.fixture
def no_openai_base(monkeypatch):
    monkeypatch.delenv("OPENAI_API_BASE", raising=False)
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")


def test_unknown_prefix_without_endpoint_fails_loudly(no_openai_base):
    with pytest.raises(ValueError, match="Unknown LLM provider prefix 'mistral'"):
        PraisonAIModel(model="mistral/mistral-small")


def test_unknown_prefix_with_custom_endpoint_passes_through(no_openai_base):
    m = PraisonAIModel(model="meta-llama/Llama-3.1-8B", base_url="http://localhost:8000/v1")
    assert m.model_name == "meta-llama/Llama-3.1-8B"
    assert m.base_url == "http://localhost:8000/v1"


def test_unknown_prefix_with_env_endpoint_passes_through(no_openai_base, monkeypatch):
    monkeypatch.setenv("OPENAI_API_BASE", "http://gateway:4000/v1")
    m = PraisonAIModel(model="mistral/mistral-small")
    assert m.base_url == "http://gateway:4000/v1"


def test_bare_model_still_defaults_to_openai(no_openai_base):
    m = PraisonAIModel(model="gpt-4o-mini")
    assert m.base_url == "https://api.openai.com/v1"


class _Adapter:
    name = "crewai"
    SUPPORTED_YAML_FIELDS = frozenset({"llm"})


@pytest.mark.parametrize("field", ["approval", "guardrails"])
def test_dropped_safety_field_fails_closed(field):
    with pytest.raises(ValueError, match="cannot enforce safety"):
        warn_unsupported_fields(_Adapter(), {"role": "r", field: {"backend": "console"}})


def test_dropped_non_safety_field_only_warns(caplog):
    warn_unsupported_fields(_Adapter(), {"role": "r", "memory": True})
    assert "ignores YAML field" in caplog.text
