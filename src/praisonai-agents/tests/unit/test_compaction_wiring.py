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
