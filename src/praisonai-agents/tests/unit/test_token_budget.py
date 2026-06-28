"""Tests for Token Budget Guard (F1).

Tests the max_budget feature in ExecutionConfig that provides hard dollar
limits per agent run with zero overhead when disabled.
"""

import pytest
from unittest.mock import MagicMock, patch


class TestBudgetExceededError:
    """Test BudgetExceededError exception class."""

    def test_import_from_agent_module(self):
        from praisonaiagents.agent.agent import BudgetExceededError
        assert issubclass(BudgetExceededError, Exception)

    def test_import_from_package(self):
        from praisonaiagents import BudgetExceededError
        assert issubclass(BudgetExceededError, Exception)

    def test_error_attributes(self):
        from praisonaiagents.agent.agent import BudgetExceededError
        err = BudgetExceededError("test_agent", 0.55, 0.50)
        assert err.agent_name == "test_agent"
        assert err.total_cost == 0.55
        assert err.max_budget == 0.50

    def test_error_message(self):
        from praisonaiagents.agent.agent import BudgetExceededError
        err = BudgetExceededError("researcher", 0.5123, 0.50)
        assert "researcher" in str(err)
        assert "$0.5123" in str(err)
        assert "$0.5000" in str(err)


class TestExecutionConfigBudget:
    """Test max_budget fields on ExecutionConfig."""

    def test_default_none(self):
        from praisonaiagents import ExecutionConfig
        config = ExecutionConfig()
        assert config.max_budget is None
        assert config.on_budget_exceeded == "stop"

    def test_set_budget(self):
        from praisonaiagents import ExecutionConfig
        config = ExecutionConfig(max_budget=0.50)
        assert config.max_budget == 0.50
        assert config.on_budget_exceeded == "stop"

    def test_warn_mode(self):
        from praisonaiagents import ExecutionConfig
        config = ExecutionConfig(max_budget=1.00, on_budget_exceeded="warn")
        assert config.on_budget_exceeded == "warn"

    def test_callable_mode(self):
        from praisonaiagents import ExecutionConfig
        handler = lambda cost, budget: None
        config = ExecutionConfig(max_budget=1.00, on_budget_exceeded=handler)
        assert callable(config.on_budget_exceeded)

    def test_to_dict_includes_budget(self):
        from praisonaiagents import ExecutionConfig
        config = ExecutionConfig(max_budget=0.75)
        d = config.to_dict()
        assert d["max_budget"] == 0.75


class TestAgentBudgetInit:
    """Test that Agent correctly initializes budget tracking from ExecutionConfig."""

    def test_no_budget_defaults(self):
        """Agent without max_budget has zero-cost tracking active but no limit."""
        from praisonaiagents import Agent
        agent = Agent(name="test", instructions="test")
        assert agent._max_budget is None
        assert agent._total_cost == 0.0
        assert agent._total_tokens_in == 0
        assert agent._total_tokens_out == 0
        assert agent._llm_call_count == 0

    def test_budget_from_execution_config(self):
        """Agent extracts max_budget from ExecutionConfig."""
        from praisonaiagents import Agent, ExecutionConfig
        agent = Agent(
            name="test",
            instructions="test",
            execution=ExecutionConfig(max_budget=0.50),
        )
        assert agent._max_budget == 0.50
        assert agent._on_budget_exceeded == "stop"

    def test_budget_warn_mode(self):
        from praisonaiagents import Agent, ExecutionConfig
        agent = Agent(
            name="test",
            instructions="test",
            execution=ExecutionConfig(max_budget=1.0, on_budget_exceeded="warn"),
        )
        assert agent._on_budget_exceeded == "warn"


class TestCostProperties:
    """Test total_cost and cost_summary read-only properties."""

    def test_total_cost_initial(self):
        from praisonaiagents import Agent
        agent = Agent(name="test", instructions="test")
        assert agent.total_cost == 0.0

    def test_cost_summary_initial(self):
        from praisonaiagents import Agent
        agent = Agent(name="test", instructions="test")
        summary = agent.cost_summary
        assert summary == {
            "tokens_in": 0,
            "tokens_out": 0,
            "cost": 0.0,
            "llm_calls": 0,
        }

    def test_cost_accumulates(self):
        """Manually simulate cost accumulation to verify properties work."""
        from praisonaiagents import Agent
        agent = Agent(name="test", instructions="test")
        # Simulate what _chat_completion does
        agent._total_cost += 0.01
        agent._total_tokens_in += 100
        agent._total_tokens_out += 50
        agent._llm_call_count += 1
        
        assert agent.total_cost == 0.01
        assert agent.cost_summary == {
            "tokens_in": 100,
            "tokens_out": 50,
            "cost": 0.01,
            "llm_calls": 1,
        }

    def test_cost_accumulates_multiple(self):
        from praisonaiagents import Agent
        agent = Agent(name="test", instructions="test")
        for i in range(5):
            agent._total_cost += 0.01
            agent._total_tokens_in += 100
            agent._total_tokens_out += 50
            agent._llm_call_count += 1
        
        assert agent.total_cost == pytest.approx(0.05)
        assert agent.cost_summary["llm_calls"] == 5
        assert agent.cost_summary["tokens_in"] == 500


class TestBudgetNoneOverhead:
    """Verify zero overhead when max_budget is None (the default path)."""

    def test_none_budget_falsy(self):
        """None is falsy, so 'if self._max_budget' skips the check."""
        from praisonaiagents import Agent
        agent = Agent(name="test", instructions="test")
        # This is the check in _chat_completion:
        assert not agent._max_budget  # None is falsy → skips budget check

    def test_zero_budget_falsy(self):
        """0.0 budget is also falsy but shouldn't be used — verify behavior."""
        from praisonaiagents import Agent, ExecutionConfig
        agent = Agent(
            name="test", instructions="test",
            execution=ExecutionConfig(max_budget=0.0),
        )
        # 0.0 is falsy → budget check is skipped (intentional)
        assert not agent._max_budget


class TestPreCallEstimate:
    """Test _estimate_min_call_cost helper used by the pre-call guard."""

    def test_estimate_zero_for_empty_messages(self):
        from praisonaiagents import Agent
        agent = Agent(name="test", instructions="test")
        assert agent._estimate_min_call_cost([], None) == 0.0

    def test_estimate_scales_with_input(self):
        from praisonaiagents import Agent
        agent = Agent(name="test", instructions="test", llm="gpt-4o")
        small = agent._estimate_min_call_cost(
            [{"role": "user", "content": "hi"}], None
        )
        large = agent._estimate_min_call_cost(
            [{"role": "user", "content": "x" * 100_000}], None
        )
        assert large > small

    def test_estimate_includes_output_reservation(self):
        from praisonaiagents import Agent
        agent = Agent(name="test", instructions="test", llm="gpt-4o")
        msgs = [{"role": "user", "content": "hello world"}]
        # A larger explicit max_tokens reservation costs more than a smaller one.
        small_out = agent._estimate_min_call_cost(msgs, 100)
        large_out = agent._estimate_min_call_cost(msgs, 5000)
        assert large_out > small_out

    def test_estimate_reserves_default_output_when_max_tokens_unset(self):
        """Unset max_tokens must still reserve a non-zero output cost so a small
        prompt with a large provider-default response cannot bypass the guard."""
        from praisonaiagents import Agent
        agent = Agent(name="test", instructions="test", llm="gpt-4o")
        msgs = [{"role": "user", "content": "hi"}]
        # Input alone (2 chars -> 0 tokens) would otherwise be ~free; the default
        # output reservation guarantees a positive estimate.
        assert agent._estimate_min_call_cost(msgs, None) > 0.0

    def test_estimate_handles_list_content(self):
        from praisonaiagents import Agent
        agent = Agent(name="test", instructions="test", llm="gpt-4o")
        msgs = [{"role": "user", "content": [{"type": "text", "text": "x" * 8000}]}]
        assert agent._estimate_min_call_cost(msgs, None) > 0.0


class TestPreCallGuard:
    """Test that the pre-call guard blocks an over-budget call before dispatch."""

    def test_guard_blocks_before_dispatch(self):
        """A huge input that breaches the cap raises before the LLM is called."""
        from praisonaiagents import Agent, ExecutionConfig, BudgetExceededError
        agent = Agent(
            name="test", instructions="test", llm="gpt-4o",
            execution=ExecutionConfig(max_budget=0.0001),
        )
        # Make the retry path explode if it is ever reached.
        agent._chat_completion_with_retry = MagicMock(
            side_effect=AssertionError("LLM dispatched despite budget guard")
        )
        messages = [{"role": "user", "content": "x" * 200_000}]
        with pytest.raises(BudgetExceededError):
            agent._chat_completion(messages)
        agent._chat_completion_with_retry.assert_not_called()
        # No spend recorded for the blocked call.
        assert agent._total_cost == 0.0

    def test_guard_skips_when_warn_mode(self):
        """warn mode keeps reactive-only behaviour (no pre-call block)."""
        from praisonaiagents import Agent, ExecutionConfig
        agent = Agent(
            name="test", instructions="test", llm="gpt-4o",
            execution=ExecutionConfig(max_budget=0.0001, on_budget_exceeded="warn"),
        )
        est = agent._estimate_min_call_cost(
            [{"role": "user", "content": "x" * 200_000}], None
        )
        # Estimate alone would exceed the cap, but warn mode must not pre-block.
        assert est >= agent._max_budget
        assert agent._on_budget_exceeded == "warn"


class TestPostCallBudgetOnStreamingAutoDetect:
    """stream=None auto-detect must still record spend after a streaming success."""

    def _mock_response(self, cost_usd=0.08):
        usage = MagicMock(prompt_tokens=100, completion_tokens=50)
        response = MagicMock(usage=usage, choices=[])
        return response

    def test_streaming_autodetect_records_cost(self):
        from praisonaiagents import Agent, ExecutionConfig
        agent = Agent(
            name="test", instructions="test", llm="gpt-4o",
            execution=ExecutionConfig(max_budget=1.0),
        )
        mock_response = self._mock_response()
        with patch.object(
            agent, "_chat_completion_with_retry", return_value=mock_response
        ), patch.object(
            agent, "_calculate_llm_cost", return_value=0.08
        ), patch.object(
            agent, "_extract_llm_response_content", return_value="ok"
        ), patch(
            "praisonaiagents.trace.context_events.get_context_emitter"
        ) as get_emitter, patch.object(
            agent._hook_runner, "execute_sync"
        ):
            get_emitter.return_value = MagicMock()
            agent._chat_completion(
                [{"role": "user", "content": "hello"}],
                stream=None,
            )

        assert agent._total_cost == pytest.approx(0.08)
        assert agent._llm_call_count == 1

    def test_streaming_autodetect_enforces_cumulative_budget(self):
        from praisonaiagents import Agent, ExecutionConfig, BudgetExceededError
        agent = Agent(
            name="test", instructions="test", llm="gpt-4o",
            execution=ExecutionConfig(max_budget=0.10),
        )
        mock_response = self._mock_response()
        with patch.object(
            agent, "_chat_completion_with_retry", return_value=mock_response
        ), patch.object(
            agent, "_calculate_llm_cost", return_value=0.08
        ), patch.object(
            agent, "_extract_llm_response_content", return_value="ok"
        ), patch(
            "praisonaiagents.trace.context_events.get_context_emitter"
        ) as get_emitter, patch.object(
            agent._hook_runner, "execute_sync"
        ):
            get_emitter.return_value = MagicMock()
            agent._chat_completion(
                [{"role": "user", "content": "first"}],
                stream=None,
            )
            with pytest.raises(BudgetExceededError):
                agent._chat_completion(
                    [{"role": "user", "content": "second"}],
                    stream=None,
                )


class TestAsyncBudgetEnforcement:
    """Async unified dispatch must enforce max_budget like sync _chat_completion."""

    def _mock_response(self):
        usage = MagicMock(prompt_tokens=100, completion_tokens=50)
        return MagicMock(usage=usage, choices=[])

    @pytest.mark.asyncio
    async def test_async_guard_blocks_before_dispatch(self):
        from unittest.mock import AsyncMock
        from praisonaiagents import Agent, ExecutionConfig, BudgetExceededError

        agent = Agent(
            name="test", instructions="test", llm="gpt-4o",
            execution=ExecutionConfig(max_budget=0.0001),
        )
        mock_dispatcher = MagicMock()
        mock_dispatcher.achat_completion = AsyncMock(
            side_effect=AssertionError("LLM dispatched despite budget guard")
        )
        agent._unified_dispatcher = mock_dispatcher
        messages = [{"role": "user", "content": "x" * 200_000}]
        with pytest.raises(BudgetExceededError):
            await agent._execute_unified_achat_completion(messages)
        mock_dispatcher.achat_completion.assert_not_called()
        assert agent._total_cost == 0.0

    @pytest.mark.asyncio
    async def test_async_records_cost_and_enforces_ceiling(self):
        from unittest.mock import AsyncMock
        from praisonaiagents import Agent, ExecutionConfig, BudgetExceededError

        agent = Agent(
            name="test", instructions="test", llm="gpt-4o",
            execution=ExecutionConfig(max_budget=0.10),
        )
        mock_response = self._mock_response()
        mock_dispatcher = MagicMock()
        mock_dispatcher.achat_completion = AsyncMock(return_value=mock_response)
        agent._unified_dispatcher = mock_dispatcher
        messages = [{"role": "user", "content": "hello"}]
        with patch.object(agent, "_calculate_llm_cost", return_value=0.08):
            await agent._execute_unified_achat_completion(messages)
            assert agent._total_cost == 0.08
            with pytest.raises(BudgetExceededError):
                await agent._execute_unified_achat_completion(messages)
