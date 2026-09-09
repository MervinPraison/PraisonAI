"""Regression tests for YAML model-aware output budgets."""

from praisonai.framework_adapters.praisonai_adapter import (
    _build_agent_llm_spec,
    _resolve_output_budget,
)


def test_yaml_budget_uses_output_ceiling_for_omitted_value(monkeypatch):
    monkeypatch.setattr(
        "praisonaiagents.llm.model_capabilities.max_output_tokens",
        lambda model: 8192,
    )

    assert _resolve_output_budget("provider/model") == 8192
    assert _resolve_output_budget("provider/model", 12000) == 8192


def test_yaml_llm_spec_preserves_provider_options():
    raw = {
        "model": "provider/model",
        "temperature": 0.2,
        "api_base": "http://localhost:11434",
        "retry": {"max_attempts": 2},
    }

    resolved = _build_agent_llm_spec(raw, "provider/model", 4096)

    assert resolved == {
        **raw,
        "max_tokens": 4096,
    }
    assert resolved is not raw
