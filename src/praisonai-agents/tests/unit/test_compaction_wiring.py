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
        # A short conversation should fit under both accurate and heuristic
        # token counting; assert the fixture's budget premise explicitly.
        msgs = [{"role": "user", "content": "message " * 30000}]
        compactor = ContextCompactor(max_tokens=resolved)
        assert compactor.count_total_tokens(msgs) < resolved
        assert compactor.needs_compaction(msgs) is False

    def test_unset_triggers_when_budget_approached(self):
        from praisonaiagents.config.feature_configs import ExecutionConfig
        from praisonaiagents.compaction import ContextCompactor
        agent = self._make_agent("gpt-4o")
        cfg = ExecutionConfig(context_compaction=True)
        resolved = agent._resolve_compaction_max_tokens(cfg)
        # Well beyond the working budget must trigger compaction.
        # Repeated A characters compress under BPE: char/4 does not establish
        # that an accurate tokeniser sees an over-budget conversation.
        msgs = [{"role": "user", "content": "message " * (resolved + 50000)}]
        compactor = ContextCompactor(max_tokens=resolved)
        assert compactor.count_total_tokens(msgs) > resolved
        assert compactor.needs_compaction(msgs) is True


class TestCompactionEntryPointWiring:
    """Both sync and async entry points must pass the resolved model-aware
    budget to ContextCompactor when max_context_tokens is unset.

    These guard against a regression where an entry point stops forwarding the
    resolved budget (e.g. reverting to a flat default), which the resolver-only
    tests above would not catch.
    """

    def _make_agent(self, model):
        from praisonaiagents.agent.agent import Agent
        return Agent(name="t", instructions="t", llm=model)

    def _capture_max_tokens(self):
        captured = {}

        class _FakeCompactor:
            def __init__(self, max_tokens=None, strategy=None, llm_summarize_fn=None):
                captured["max_tokens"] = max_tokens

            def needs_compaction(self, messages):
                return False  # short-circuit; we only assert the wired budget

        return captured, _FakeCompactor

    def test_sync_entry_point_wires_resolved_budget(self):
        from praisonaiagents.config.feature_configs import ExecutionConfig
        from praisonaiagents.hooks.types import HookEvent

        agent = self._make_agent("gpt-4o")  # 128k window
        agent.execution = ExecutionConfig(context_compaction=True)  # unset limit
        expected = agent._resolve_compaction_max_tokens(agent.execution)
        assert expected > 8000  # model-aware, not the old flat default

        captured, fake = self._capture_max_tokens()
        with patch("praisonaiagents.compaction.ContextCompactor", fake):
            agent._apply_context_compaction([{"role": "user", "content": "hi"}], HookEvent)
        assert captured["max_tokens"] == expected

    @pytest.mark.asyncio
    async def test_async_entry_point_wires_resolved_budget(self):
        from praisonaiagents.config.feature_configs import ExecutionConfig
        from praisonaiagents.hooks.types import HookEvent

        agent = self._make_agent("gpt-4o")  # 128k window
        agent.execution = ExecutionConfig(context_compaction=True)  # unset limit
        expected = agent._resolve_compaction_max_tokens(agent.execution)
        assert expected > 8000

        captured, fake = self._capture_max_tokens()
        with patch("praisonaiagents.compaction.ContextCompactor", fake):
            await agent._apply_context_compaction_async(
                [{"role": "user", "content": "hi"}], HookEvent
            )
        assert captured["max_tokens"] == expected


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
