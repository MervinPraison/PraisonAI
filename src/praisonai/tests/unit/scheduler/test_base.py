"""
Unit tests for scheduler base components.

Tests for:
- ScheduleParser
- ExecutorInterface
- PraisonAgentExecutor
"""

import pytest
from unittest.mock import Mock, patch
from praisonai.scheduler.base import ScheduleParser, ExecutorInterface, PraisonAgentExecutor
from praisonai.scheduler._base_scheduler import (
    _compute_run_cost,
    _extract_usage,
    _to_non_negative_int,
)


class TestScheduleParser:
    """Test ScheduleParser schedule expression parsing."""
    
    def test_parse_hourly(self):
        """Test parsing 'hourly' returns 3600 seconds."""
        result = ScheduleParser.parse("hourly")
        assert result == 3600
    
    def test_parse_daily(self):
        """Test parsing 'daily' returns 86400 seconds."""
        result = ScheduleParser.parse("daily")
        assert result == 86400
    
    def test_parse_minutes_format(self):
        """Test parsing '*/30m' returns 1800 seconds."""
        result = ScheduleParser.parse("*/30m")
        assert result == 1800
    
    def test_parse_hours_format(self):
        """Test parsing '*/6h' returns 21600 seconds."""
        result = ScheduleParser.parse("*/6h")
        assert result == 21600
    
    def test_parse_plain_number(self):
        """Test parsing '3600' returns 3600 seconds."""
        result = ScheduleParser.parse("3600")
        assert result == 3600
    
    def test_parse_invalid_format(self):
        """Test parsing invalid format raises ValueError."""
        with pytest.raises(ValueError, match="Unsupported schedule format"):
            ScheduleParser.parse("invalid_format")
    
    def test_parse_case_insensitive(self):
        """Test parsing is case insensitive."""
        assert ScheduleParser.parse("HOURLY") == 3600
        assert ScheduleParser.parse("Daily") == 86400
    
    def test_parse_with_whitespace(self):
        """Test parsing handles whitespace."""
        assert ScheduleParser.parse("  hourly  ") == 3600
    
    def test_parse_seconds_format(self):
        """Test parsing '*/30s' returns 30 seconds."""
        result = ScheduleParser.parse("*/30s")
        assert result == 30
    
    def test_parse_various_minutes(self):
        """Test parsing various minute formats."""
        assert ScheduleParser.parse("*/1m") == 60
        assert ScheduleParser.parse("*/15m") == 900
        assert ScheduleParser.parse("*/45m") == 2700
    
    def test_parse_various_hours(self):
        """Test parsing various hour formats."""
        assert ScheduleParser.parse("*/1h") == 3600
        assert ScheduleParser.parse("*/2h") == 7200
        assert ScheduleParser.parse("*/12h") == 43200

    def test_parse_cron_interval(self):
        """Cron "*/N * * * *" -> every N minutes."""
        assert ScheduleParser.parse("cron:*/15 * * * *") == 900

    def test_parse_cron_hourly(self):
        """Cron "M * * * *" -> hourly."""
        assert ScheduleParser.parse("cron:30 * * * *") == 3600

    def test_parse_cron_daily(self):
        """Cron "M H * * *" -> daily."""
        assert ScheduleParser.parse("cron:0 8 * * *") == 86400
        assert ScheduleParser.parse("cron:0 17 * * 1-5") == 86400

    def test_parse_cron_daily_case_insensitive(self):
        """Cron prefix is case-insensitive."""
        assert ScheduleParser.parse("CRON:0 8 * * *") == 86400

    def test_parse_cron_fallback(self):
        """Complex cron patterns (ranges/lists) fall back to 60 seconds."""
        assert ScheduleParser.parse("cron:0 8,12 * * *") == 60


class TestExecutorInterface:
    """Test ExecutorInterface abstract class."""
    
    def test_cannot_instantiate_interface(self):
        """Test ExecutorInterface cannot be instantiated directly."""
        with pytest.raises(TypeError):
            ExecutorInterface()
    
    def test_must_implement_execute(self):
        """Test subclass must implement execute method."""
        class IncompleteExecutor(ExecutorInterface):
            pass
        
        with pytest.raises(TypeError):
            IncompleteExecutor()
    
    def test_valid_implementation(self):
        """Test valid implementation of ExecutorInterface."""
        class ValidExecutor(ExecutorInterface):
            def execute(self, task: str):
                return "result"
        
        executor = ValidExecutor()
        assert executor.execute("test") == "result"


class TestPraisonAgentExecutor:
    """Test PraisonAgentExecutor implementation."""
    
    def test_init_with_agent(self):
        """Test initialization with agent."""
        mock_agent = Mock()
        executor = PraisonAgentExecutor(mock_agent)
        assert executor.agent == mock_agent
    
    def test_execute_success(self):
        """Test successful execution."""
        mock_agent = Mock()
        executor = PraisonAgentExecutor(mock_agent)
        with patch('praisonai.scheduler.base.run_sync', return_value="Agent result"):
            result = executor.execute("Test task")
        
        assert result == "Agent result"
    
    def test_execute_failure(self):
        """Test execution failure raises exception."""
        mock_agent = Mock()
        executor = PraisonAgentExecutor(mock_agent)
        
        with patch('praisonai.scheduler.base.run_sync', side_effect=Exception("Agent error")):
            with pytest.raises(Exception, match="Agent error"):
                executor.execute("Test task")
    
    def test_execute_with_different_tasks(self):
        """Test execution with different tasks."""
        mock_agent = Mock()
        executor = PraisonAgentExecutor(mock_agent)
        
        with patch(
            'praisonai.scheduler.base.run_sync',
            side_effect=["Result for: Task 1", "Result for: Task 2"],
        ):
            result1 = executor.execute("Task 1")
            result2 = executor.execute("Task 2")
        
        assert result1 == "Result for: Task 1"
        assert result2 == "Result for: Task 2"


class TestComputeRunCost:
    """Regression tests for token-usage-based run cost computation."""

    def test_to_non_negative_int_clamps_and_coerces(self):
        """Negative or malformed token values clamp to 0; valid values pass through."""
        assert _to_non_negative_int(-5) == 0
        assert _to_non_negative_int("bad") == 0
        assert _to_non_negative_int(None) == 0
        assert _to_non_negative_int("7") == 7
        assert _to_non_negative_int(12) == 12

    def test_no_usage_returns_zero_cost(self):
        """A response with no usage metadata contributes $0, not a fake constant."""
        cost, in_tok, out_tok, model = _compute_run_cost({})
        assert cost == 0.0
        assert in_tok == 0
        assert out_tok == 0

    def test_dict_usage_computes_cost(self):
        """Dict-style usage with a known model produces a positive cost."""
        result = {
            "usage": {"input_tokens": 1_000_000, "output_tokens": 0},
            "model": "gpt-4o-mini",
        }
        cost, in_tok, out_tok, model = _compute_run_cost(result)
        assert in_tok == 1_000_000
        assert out_tok == 0
        assert model == "gpt-4o-mini"
        assert cost == pytest.approx(0.15)

    def test_attr_usage_computes_cost(self):
        """Attribute-style usage objects are supported."""
        usage = Mock(spec=["input_tokens", "output_tokens"])
        usage.input_tokens = 0
        usage.output_tokens = 1_000_000
        result = Mock(spec=["usage", "model"])
        result.usage = usage
        result.model = "gpt-4o-mini"
        cost, in_tok, out_tok, model = _compute_run_cost(result)
        assert out_tok == 1_000_000
        assert cost == pytest.approx(0.60)

    def test_missing_model_uses_default_pricing_not_first_entry(self):
        """Usage present but no model must use the 'default' tier, not gpt-4o.

        Regression: get_pricing("") substring-matched the first DEFAULT_PRICING
        entry (gpt-4o, $2.50/$10) instead of the intended default ($1/$3).
        """
        result = {"usage": {"input_tokens": 1_000_000, "output_tokens": 1_000_000}}
        cost, _, _, model = _compute_run_cost(result)
        assert model == ""
        # default tier: 1.00 + 3.00 == 4.00, NOT gpt-4o's 2.50 + 10.00 == 12.50
        assert cost == pytest.approx(4.0)

    def test_negative_tokens_do_not_produce_negative_cost(self):
        """Negative usage values are clamped, preventing a budget-brake bypass."""
        result = {
            "usage": {"input_tokens": -100, "output_tokens": -50},
            "model": "gpt-4o",
        }
        cost, in_tok, out_tok, _ = _compute_run_cost(result)
        assert cost == 0.0
        assert in_tok == 0
        assert out_tok == 0

    def test_pricing_failure_is_isolated_to_zero_cost(self, monkeypatch):
        """A failure inside cost computation must not raise into the run path."""
        import praisonai.cli.features.cost_tracker as cost_tracker

        def _boom(_model):
            raise RuntimeError("pricing backend down")

        monkeypatch.setattr(cost_tracker, "get_pricing", _boom)
        result = {"usage": {"input_tokens": 100, "output_tokens": 100}, "model": "gpt-4o"}
        cost, in_tok, out_tok, _ = _compute_run_cost(result)
        assert cost == 0.0
        assert in_tok == 100
        assert out_tok == 100
