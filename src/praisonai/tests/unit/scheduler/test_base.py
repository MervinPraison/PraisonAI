"""
Unit tests for scheduler base components.

Tests for:
- ScheduleParser
- ExecutorInterface
- PraisonAgentExecutor
"""

import pytest
from unittest.mock import Mock
from praisonai.scheduler.base import ScheduleParser, ExecutorInterface, PraisonAgentExecutor


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
        mock_agent.start = Mock(return_value="Agent result")
        
        executor = PraisonAgentExecutor(mock_agent)
        result = executor.execute("Test task")
        
        assert result == "Agent result"
        mock_agent.start.assert_called_once_with("Test task")
    
    def test_execute_failure(self):
        """Test execution failure raises exception."""
        mock_agent = Mock()
        mock_agent.start = Mock(side_effect=Exception("Agent error"))
        
        executor = PraisonAgentExecutor(mock_agent)
        
        with pytest.raises(Exception, match="Agent error"):
            executor.execute("Test task")
    
    def test_execute_with_different_tasks(self):
        """Test execution with different tasks."""
        mock_agent = Mock()
        mock_agent.start = Mock(side_effect=lambda task: f"Result for: {task}")
        
        executor = PraisonAgentExecutor(mock_agent)
        
        result1 = executor.execute("Task 1")
        result2 = executor.execute("Task 2")
        
        assert result1 == "Result for: Task 1"
        assert result2 == "Result for: Task 2"
        assert mock_agent.start.call_count == 2
