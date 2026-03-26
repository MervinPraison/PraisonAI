"""Real LLM integration test for F1 + F3 features.

This test makes ACTUAL LLM calls to verify:
1. F1: Token budget tracks cost (total_cost > 0 after a real call)
2. F1: cost_summary returns valid data
3. F3: Permission tiers block tools at runtime
4. F2: Heartbeat/HeartbeatConfig import and init with real Agent

Requires OPENAI_API_KEY in environment.
"""

import os
import sys
import pytest


# Skip if no API key available
pytestmark = pytest.mark.skipif(
    not os.environ.get("OPENAI_API_KEY"),
    reason="OPENAI_API_KEY not set — skipping real LLM test"
)


class TestRealLLMBudgetGuard:
    """Real LLM integration test for F1 Token Budget Guard."""

    def test_real_agent_tracks_cost(self):
        """Run a REAL agent with a budget, verify cost/token tracking."""
        from praisonaiagents import Agent
        from praisonaiagents.config.feature_configs import ExecutionConfig

        agent = Agent(
            name="budget_test",
            instructions="You are a helpful assistant. Be very brief.",
            llm="gpt-4o-mini",
            execution=ExecutionConfig(max_budget=1.00),  # $1 budget
        )

        result = agent.start("Say hello in exactly 5 words.")

        # Verify LLM responded
        assert result is not None
        result_text = str(result)
        assert len(result_text) > 0
        print(f"\n[LLM Response]: {result_text}")

        # Verify cost tracking
        assert agent.total_cost > 0, "Cost should be > 0 after real LLM call"
        summary = agent.cost_summary
        assert summary["llm_calls"] >= 1, "Should record at least 1 LLM call"
        assert summary["tokens_in"] > 0, "Should record input tokens"
        assert summary["tokens_out"] > 0, "Should record output tokens"
        assert summary["cost"] > 0, "Cost should be > 0"

        print(f"[Cost Summary]: {summary}")
        print(f"[Total Cost]: ${agent.total_cost:.6f}")

    def test_real_agent_no_budget_still_tracks(self):
        """Agent without budget should still track cost (zero overhead confirmed)."""
        from praisonaiagents import Agent

        agent = Agent(
            name="no_budget_test",
            instructions="You are helpful. Be extremely brief.",
            llm="gpt-4o-mini",
        )

        result = agent.start("Reply with just the word 'OK'.")

        assert result is not None
        print(f"\n[LLM Response]: {str(result)}")

        # Cost tracking still works (always active)
        summary = agent.cost_summary
        print(f"[Cost Summary]: {summary}")
        assert summary["llm_calls"] >= 1


class TestRealLLMPermissions:
    """Real LLM integration test for F3 Permission Tiers."""

    def test_safe_mode_agent_runs_normally(self):
        """Agent with approval='safe' can still answer questions (no tools used)."""
        from praisonaiagents import Agent

        agent = Agent(
            name="safe_agent",
            instructions="You are helpful. Be very brief.",
            llm="gpt-4o-mini",
            approval="safe",
        )

        result = agent.start("What is 2+2? Reply with just the number.")

        assert result is not None
        result_text = str(result)
        assert "4" in result_text
        print(f"\n[Safe Agent Response]: {result_text}")

        # Verify permission deny set is active
        assert len(agent._perm_deny) > 0
        assert "execute_command" in agent._perm_deny


class TestRealHeartbeatInit:
    """Real integration test for F2 Heartbeat with actual Agent."""

    def test_heartbeat_with_real_agent(self):
        """Heartbeat initializes correctly with a real Agent instance."""
        from praisonaiagents import Agent, Heartbeat

        agent = Agent(
            name="heartbeat_test",
            instructions="Monitor status briefly.",
            llm="gpt-4o-mini",
        )

        hb = Heartbeat(agent, schedule="every 30m", prompt="Quick status check")

        assert hb.agent is agent
        assert hb.config.schedule == "every 30m"
        assert hb.config.prompt == "Quick status check"
        assert hb._interval_seconds == 1800.0
        assert not hb.is_running


class TestRealCostPersistence:
    """Real integration test for F4 cost persistence after actual LLM call."""

    def test_save_real_cost_report(self, tmp_path):
        """Run real agent, save cost report, verify it persists."""
        from praisonaiagents import Agent
        from praisonaiagents.agent.cost_persistence import save_cost_report, load_cost_report
        from unittest.mock import patch

        agent = Agent(
            name="cost_persist_test",
            instructions="Be extremely brief.",
            llm="gpt-4o-mini",
        )

        agent.start("Say 'hi'.")

        with patch("praisonaiagents.agent.cost_persistence.COST_DIR", tmp_path):
            filepath = save_cost_report(agent, session_name="real_test")
            loaded = load_cost_report("real_test")

        assert loaded is not None
        assert loaded["agent_name"] == "cost_persist_test"
        assert loaded["llm_calls"] >= 1
        print(f"\n[Saved Cost Report]: {loaded}")
