"""Unit tests for Agent instantiation performance optimisations (lazy LLM, LoopGuard)."""

from __future__ import annotations

import warnings
from unittest.mock import Mock, patch

import pytest

from praisonaiagents import Agent
from praisonaiagents.config.feature_configs import ExecutionConfig
from praisonaiagents.config.loader import clear_config_cache


class TestLazyInstantiation:
    def test_agent_init_no_deprecation_warning(self):
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            Agent(name="T", output="silent")
            Agent(name="T", model="gpt-4o-mini", output="silent")
        deprecations = [w for w in caught if issubclass(w.category, DeprecationWarning)]
        assert not deprecations

    def test_litellm_model_deferred_at_init(self):
        agent = Agent(name="T", model="openai/gpt-4o-mini", output="silent")
        assert agent._llm_instance is None
        assert agent._llm_init_params["model"] == "openai/gpt-4o-mini"
        assert agent._using_custom_llm

    def test_loop_guard_deferred_at_init(self):
        agent = Agent(name="T", output="silent")
        assert agent._loop_guard is None
        guard = agent._ensure_loop_guard()
        assert guard is not None
        assert agent._ensure_loop_guard() is guard

    def test_llm_instance_materializes_once(self):
        with patch("praisonaiagents.llm.llm.LLM") as MockLLM:
            MockLLM.return_value = Mock()
            agent = Agent(name="T", model="openai/gpt-4o-mini", output="silent")
            first = agent.llm_instance
            second = agent.llm_instance
            assert first is second
            MockLLM.assert_called_once()

    def test_dict_llm_stores_max_iter_in_deferred_params(self):
        agent = Agent(
            name="T",
            llm={"model": "gpt-4o-mini", "api_key": "x"},
            execution=ExecutionConfig(max_iter=12),
            output="silent",
        )
        assert agent._llm_init_params["max_iter"] == 12

    def test_plain_model_string_no_custom_llm(self):
        agent = Agent(name="T", model="gpt-4o-mini", output="silent")
        assert not agent._using_custom_llm
        assert agent._llm_init_params is None

    def test_config_defaults_fast_path_when_empty(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        clear_config_cache()
        agent = Agent(name="T", output="silent")
        assert agent.name == "T"

    def test_execution_config_internal_from_tests_is_suppressed(self):
        """Test/SDK paths suppress context_compaction spam during Agent init."""
        ExecutionConfig._context_compaction_warned = False  # noqa: SLF001
        ExecutionConfig._context_compaction_internal = False  # noqa: SLF001
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            ExecutionConfig()
        compaction = [w for w in caught if "context_compaction" in str(w.message)]
        assert not compaction
        assert ExecutionConfig._context_compaction_internal is True  # noqa: SLF001
