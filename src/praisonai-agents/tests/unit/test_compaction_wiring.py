"""
TDD tests for compaction wiring into agent.

Tests are written BEFORE implementation (TDD).
Verifies ExecutionConfig gets context_compaction field,
and ContextCompactor is called when enabled.
"""

import pytest
from unittest.mock import MagicMock, patch


class TestExecutionConfigCompactionFields:
    """ExecutionConfig must have context_compaction and max_context_tokens fields."""

    def test_has_context_compaction_field(self):
        from praisonaiagents.config.feature_configs import ExecutionConfig
        cfg = ExecutionConfig()
        assert hasattr(cfg, "context_compaction")
        assert cfg.context_compaction is False  # safe default

    def test_has_max_context_tokens_field(self):
        from praisonaiagents.config.feature_configs import ExecutionConfig
        cfg = ExecutionConfig()
        assert hasattr(cfg, "max_context_tokens")
        assert cfg.max_context_tokens is None  # auto by default

    def test_context_compaction_opt_in(self):
        from praisonaiagents.config.feature_configs import ExecutionConfig
        cfg = ExecutionConfig(context_compaction=True, max_context_tokens=8000)
        assert cfg.context_compaction is True
        assert cfg.max_context_tokens == 8000


class TestContextCompactorExists:
    """ContextCompactor must be importable and functional (existing module)."""

    def test_import(self):
        from praisonaiagents.compaction import ContextCompactor
        assert ContextCompactor is not None

    def test_needs_compaction_false_within_limit(self):
        from praisonaiagents.compaction import ContextCompactor
        compactor = ContextCompactor(max_tokens=10000)
        short_msgs = [{"role": "user", "content": "Hello"}, {"role": "assistant", "content": "Hi"}]
        assert compactor.needs_compaction(short_msgs) is False

    def test_needs_compaction_true_over_limit(self):
        from praisonaiagents.compaction import ContextCompactor
        compactor = ContextCompactor(max_tokens=10)  # tiny limit
        long_msgs = [{"role": "user", "content": "A" * 1000}]
        assert compactor.needs_compaction(long_msgs) is True

    def test_compact_reduces_tokens(self):
        from praisonaiagents.compaction import ContextCompactor
        compactor = ContextCompactor(max_tokens=100, preserve_recent=1)
        many_msgs = [{"role": "user", "content": "Message " + str(i) * 50} for i in range(20)]
        compacted_msgs, result = compactor.compact(many_msgs)
        assert result.compacted_tokens < result.original_tokens


class TestCompactionMaxTokensResolution:
    """When max_context_tokens is unset, trigger must size to the model window."""

    def _make_agent(self, model):
        from praisonaiagents.agent.agent import Agent
        return Agent(name="t", instructions="t", llm=model)

    def test_explicit_max_context_tokens_wins(self):
        from praisonaiagents.config.feature_configs import ExecutionConfig
        agent = self._make_agent("gpt-4o")
        cfg = ExecutionConfig(context_compaction=True, max_context_tokens=8000)
        assert agent._resolve_compaction_max_tokens(cfg) == 8000

    def test_unset_derives_from_large_model_window(self):
        from praisonaiagents.config.feature_configs import ExecutionConfig
        agent = self._make_agent("gpt-4o")  # 128k window
        cfg = ExecutionConfig(context_compaction=True)  # max_context_tokens unset
        resolved = agent._resolve_compaction_max_tokens(cfg)
        # Must be far above the old flat 8000 for a large-context model.
        assert resolved > 8000

    def test_unset_does_not_trigger_within_window(self):
        from praisonaiagents.config.feature_configs import ExecutionConfig
        from praisonaiagents.compaction import ContextCompactor
        agent = self._make_agent("gpt-4o")  # 128k window
        cfg = ExecutionConfig(context_compaction=True)
        resolved = agent._resolve_compaction_max_tokens(cfg)
        # ~30k tokens of conversation should fit comfortably in a 128k model.
        msgs = [{"role": "user", "content": "A" * 4 * 30000}]
        compactor = ContextCompactor(max_tokens=resolved)
        assert compactor.needs_compaction(msgs) is False

    def test_unset_triggers_when_budget_approached(self):
        from praisonaiagents.config.feature_configs import ExecutionConfig
        from praisonaiagents.compaction import ContextCompactor
        agent = self._make_agent("gpt-4o")
        cfg = ExecutionConfig(context_compaction=True)
        resolved = agent._resolve_compaction_max_tokens(cfg)
        # Well beyond the working budget must trigger compaction.
        msgs = [{"role": "user", "content": "A" * 4 * (resolved + 50000)}]
        compactor = ContextCompactor(max_tokens=resolved)
        assert compactor.needs_compaction(msgs) is True


class TestCompactionHookEvents:
    """BEFORE_COMPACTION and AFTER_COMPACTION must be defined in HookEvent."""

    def test_before_compaction_event_exists(self):
        from praisonaiagents.hooks.types import HookEvent
        assert hasattr(HookEvent, "BEFORE_COMPACTION")
        assert HookEvent.BEFORE_COMPACTION == "before_compaction"

    def test_after_compaction_event_exists(self):
        from praisonaiagents.hooks.types import HookEvent
        assert hasattr(HookEvent, "AFTER_COMPACTION")
        assert HookEvent.AFTER_COMPACTION == "after_compaction"
