"""Tests that auxiliary/internal LLM calls route through the configured
``small_model`` (issue #3494).

Covers the two live auxiliary call sites that previously always used the
primary agent model:

* the compaction/summarisation function built by
  ``Agent._create_llm_summarize_fn``; and
* LLM guardrail construction on both ``Agent`` and ``Task``.

Behaviour stays backward-compatible: when no ``small_model`` is configured the
primary model is used, exactly as before.
"""

from unittest.mock import MagicMock, patch

import pytest

from praisonaiagents.agent.agent import Agent


class _StubDefaults:
    def __init__(self, small_model=None, model=None):
        self.small_model = small_model
        self.model = model


def _patch_small_model(monkeypatch, small_model):
    """Force ``get_small_model`` config lookups to return ``small_model``."""
    from praisonaiagents.config import loader

    monkeypatch.setattr(
        loader, "get_default",
        lambda key, default=None: small_model if key == "small_model" else default,
    )
    monkeypatch.setattr(loader, "_agent_section_value", lambda key: None)


class TestSummarizeFnRouting:
    def test_uses_small_model_when_configured(self, monkeypatch):
        _patch_small_model(monkeypatch, "cheap-model")
        agent = Agent(instructions="test", llm="primary-model")

        captured = {}
        fake_client = MagicMock()

        def _create(model, **kwargs):
            captured["model"] = model
            resp = MagicMock()
            resp.choices[0].message.content = "summary"
            return resp

        fake_client.chat.completions.create.side_effect = _create

        with patch(
            "praisonaiagents.agent.agent._get_llm_functions",
            return_value={"get_openai_client": lambda *a, **k: fake_client},
        ):
            fn = agent._create_llm_summarize_fn()
            fn([{"role": "user", "content": "hello"}])

        assert captured["model"] == "cheap-model"

    def test_falls_back_to_primary_when_unset(self, monkeypatch):
        _patch_small_model(monkeypatch, None)
        agent = Agent(instructions="test", llm="primary-model")

        captured = {}
        fake_client = MagicMock()

        def _create(model, **kwargs):
            captured["model"] = model
            resp = MagicMock()
            resp.choices[0].message.content = "summary"
            return resp

        fake_client.chat.completions.create.side_effect = _create

        with patch(
            "praisonaiagents.agent.agent._get_llm_functions",
            return_value={"get_openai_client": lambda *a, **k: fake_client},
        ):
            fn = agent._create_llm_summarize_fn()
            fn([{"role": "user", "content": "hello"}])

        assert captured["model"] == "primary-model"


class TestGuardrailRouting:
    def test_agent_guardrail_uses_small_model(self, monkeypatch):
        _patch_small_model(monkeypatch, "cheap-model")

        captured = {}

        class _StubGuardrail:
            def __init__(self, description, llm=None):
                captured["llm"] = llm

        with patch("praisonaiagents.guardrails.LLMGuardrail", _StubGuardrail):
            Agent(instructions="test", llm="primary-model", guardrails="be nice")

        assert captured["llm"] == "cheap-model"

    def test_agent_guardrail_falls_back_to_primary(self, monkeypatch):
        _patch_small_model(monkeypatch, None)

        captured = {}

        class _StubGuardrail:
            def __init__(self, description, llm=None):
                captured["llm"] = llm

        with patch("praisonaiagents.guardrails.LLMGuardrail", _StubGuardrail):
            Agent(instructions="test", llm="primary-model", guardrails="be nice")

        assert captured["llm"] == "primary-model"


class TestTaskGuardrailRouting:
    def test_task_guardrail_uses_small_model_for_string_llm(self, monkeypatch):
        _patch_small_model(monkeypatch, "cheap-model")

        from praisonaiagents.task.task import Task

        captured = {}

        class _StubGuardrail:
            def __init__(self, description, llm=None):
                captured["llm"] = llm

        agent = Agent(instructions="test", llm="primary-model")

        with patch("praisonaiagents.guardrails.LLMGuardrail", _StubGuardrail):
            Task(description="d", expected_output="o", agent=agent, guardrail="be nice")

        assert captured["llm"] == "cheap-model"

    def test_task_guardrail_prefers_llm_instance(self, monkeypatch):
        """A configured LLM instance (with endpoint/api-key) must win over the
        bare model-name string and must NOT be rerouted to small_model."""
        _patch_small_model(monkeypatch, "cheap-model")

        from praisonaiagents.task.task import Task

        captured = {}

        class _StubGuardrail:
            def __init__(self, description, llm=None):
                captured["llm"] = llm

        agent = Agent(instructions="test", llm="primary-model")
        sentinel_instance = object()
        agent.llm_instance = sentinel_instance

        with patch("praisonaiagents.guardrails.LLMGuardrail", _StubGuardrail):
            Task(description="d", expected_output="o", agent=agent, guardrail="be nice")

        assert captured["llm"] is sentinel_instance


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
