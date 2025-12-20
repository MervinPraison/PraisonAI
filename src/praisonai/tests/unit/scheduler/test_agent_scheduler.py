"""
Unit tests for AgentScheduler.

Tests for:
- AgentScheduler initialization
- Start/stop functionality
- Execution logic
- Callbacks
- Threading
- Statistics
"""

import pytest
import time
import threading
from unittest.mock import Mock, patch, call
from praisonai.scheduler.agent_scheduler import AgentScheduler, create_agent_scheduler


class TestAgentSchedulerInit:
    """Test AgentScheduler initialization."""
    
    def test_init_with_agent_and_task(self):
        """Test initialization with agent and task."""
        mock_agent = Mock()
        scheduler = AgentScheduler(mock_agent, "Test task")
        
        assert scheduler.agent == mock_agent
        assert scheduler.task == "Test task"
        assert scheduler.is_running == False
        assert scheduler._execution_count == 0
        assert scheduler._success_count == 0
        assert scheduler._failure_count == 0
    
    def test_init_with_config(self):
        """Test initialization with optional config."""
        mock_agent = Mock()
        config = {"key": "value"}
        scheduler = AgentScheduler(mock_agent, "Test task", config=config)
        
        assert scheduler.config == config
    
    def test_init_with_callbacks(self):
        """Test initialization with callbacks."""
        mock_agent = Mock()
        on_success = Mock()
        on_failure = Mock()
        
        scheduler = AgentScheduler(
            mock_agent, 
            "Test task",
            on_success=on_success,
            on_failure=on_failure
        )
        
        assert scheduler.on_success == on_success
        assert scheduler.on_failure == on_failure
    
    def test_init_default_values(self):
        """Test initialization sets correct default values."""
        mock_agent = Mock()
        scheduler = AgentScheduler(mock_agent, "Test task")
        
        assert scheduler.config == {}
        assert scheduler.on_success is None
        assert scheduler.on_failure is None
        assert scheduler._stop_event is not None
        assert scheduler._thread is None
        assert scheduler._executor is not None


class TestAgentSchedulerStartStop:
    """Test AgentScheduler start and stop methods."""
    
    def test_start_with_valid_schedule(self):
        """Test start() with valid schedule expression."""
        mock_agent = Mock()
        scheduler = AgentScheduler(mock_agent, "Test task")
        
        result = scheduler.start("hourly", run_immediately=False)
        
        assert result == True
        assert scheduler.is_running == True
        assert scheduler._thread is not None
        assert scheduler._thread.daemon == True
        
        scheduler.stop()
    
    def test_start_already_running(self):
        """Test start() when already running returns False."""
        mock_agent = Mock()
        scheduler = AgentScheduler(mock_agent, "Test task")
        
        scheduler.start("hourly", run_immediately=False)
        result = scheduler.start("hourly", run_immediately=False)
        
        assert result == False
        
        scheduler.stop()
    
    def test_start_with_invalid_schedule(self):
        """Test start() with invalid schedule returns False."""
        mock_agent = Mock()
        scheduler = AgentScheduler(mock_agent, "Test task")
        
        result = scheduler.start("invalid_format")
        
        assert result == False
        assert scheduler.is_running == False
    
    def test_stop_when_running(self):
        """Test stop() when scheduler is running."""
        mock_agent = Mock()
        mock_agent.start = Mock(return_value="result")
        scheduler = AgentScheduler(mock_agent, "Test task")
        
        scheduler.start("*/1s", run_immediately=False)
        time.sleep(0.1)
        result = scheduler.stop()
        
        assert result == True
        assert scheduler.is_running == False
    
    def test_stop_when_not_running(self):
        """Test stop() when scheduler is not running."""
        mock_agent = Mock()
        scheduler = AgentScheduler(mock_agent, "Test task")
        
        result = scheduler.stop()
        
        assert result == True
        assert scheduler.is_running == False
    
    def test_is_running_flag(self):
        """Test is_running flag changes correctly."""
        mock_agent = Mock()
        scheduler = AgentScheduler(mock_agent, "Test task")
        
        assert scheduler.is_running == False
        
        scheduler.start("hourly", run_immediately=False)
        assert scheduler.is_running == True
        
        scheduler.stop()
        assert scheduler.is_running == False


class TestAgentSchedulerExecution:
    """Test AgentScheduler execution methods."""
    
    def test_execute_once_success(self):
        """Test execute_once() with successful execution."""
        mock_agent = Mock()
        mock_agent.start = Mock(return_value="Agent result")
        
        scheduler = AgentScheduler(mock_agent, "Test task")
        result = scheduler.execute_once()
        
        assert result == "Agent result"
        mock_agent.start.assert_called_once_with("Test task")
    
    def test_execute_once_failure(self):
        """Test execute_once() with failed execution."""
        mock_agent = Mock()
        mock_agent.start = Mock(side_effect=Exception("Agent error"))
        
        scheduler = AgentScheduler(mock_agent, "Test task")
        
        with pytest.raises(Exception, match="Agent error"):
            scheduler.execute_once()
    
    @patch('time.sleep')
    def test_execute_with_retry_success_first_try(self, mock_sleep):
        """Test _execute_with_retry() succeeds on first try."""
        mock_agent = Mock()
        mock_agent.start = Mock(return_value="Success")
        
        scheduler = AgentScheduler(mock_agent, "Test task")
        scheduler._execute_with_retry(max_retries=3)
        
        assert scheduler._success_count == 1
        assert scheduler._failure_count == 0
        mock_sleep.assert_not_called()
    
    @patch('time.sleep')
    def test_execute_with_retry_success_on_retry(self, mock_sleep):
        """Test _execute_with_retry() succeeds on retry."""
        mock_agent = Mock()
        mock_agent.start = Mock(side_effect=[
            Exception("Fail 1"),
            "Success"
        ])
        
        scheduler = AgentScheduler(mock_agent, "Test task")
        scheduler._execute_with_retry(max_retries=3)
        
        assert scheduler._success_count == 1
        assert scheduler._failure_count == 0
        assert mock_agent.start.call_count == 2
    
    @patch('time.sleep')
    def test_execute_with_retry_all_fail(self, mock_sleep):
        """Test _execute_with_retry() when all retries fail."""
        mock_agent = Mock()
        mock_agent.start = Mock(side_effect=Exception("Always fails"))
        
        scheduler = AgentScheduler(mock_agent, "Test task")
        scheduler._execute_with_retry(max_retries=3)
        
        assert scheduler._success_count == 0
        assert scheduler._failure_count == 1
        assert mock_agent.start.call_count == 3
    
    @patch('time.sleep')
    def test_execute_with_retry_exponential_backoff(self, mock_sleep):
        """Test _execute_with_retry() uses exponential backoff."""
        mock_agent = Mock()
        mock_agent.start = Mock(side_effect=Exception("Always fails"))
        
        scheduler = AgentScheduler(mock_agent, "Test task")
        scheduler._execute_with_retry(max_retries=3)
        
        # Should sleep 30s, then 60s (exponential backoff)
        assert mock_sleep.call_count == 2
        mock_sleep.assert_has_calls([call(30), call(60)])


class TestAgentSchedulerCallbacks:
    """Test AgentScheduler callback functionality."""
    
    def test_on_success_callback_invoked(self):
        """Test on_success callback is invoked on success."""
        mock_agent = Mock()
        mock_agent.start = Mock(return_value="Success result")
        on_success = Mock()
        
        scheduler = AgentScheduler(mock_agent, "Test task", on_success=on_success)
        scheduler.execute_once()
        
        on_success.assert_called_once_with("Success result")
    
    @patch('time.sleep')
    def test_on_failure_callback_invoked(self, mock_sleep):
        """Test on_failure callback is invoked on failure."""
        mock_agent = Mock()
        mock_agent.start = Mock(side_effect=Exception("Error"))
        on_failure = Mock()
        
        scheduler = AgentScheduler(mock_agent, "Test task", on_failure=on_failure)
        scheduler._execute_with_retry(max_retries=2)
        
        on_failure.assert_called_once()
    
    def test_callback_with_none(self):
        """Test execution works when callbacks are None."""
        mock_agent = Mock()
        mock_agent.start = Mock(return_value="Success")
        
        scheduler = AgentScheduler(mock_agent, "Test task")
        result = scheduler.execute_once()
        
        assert result == "Success"
    
    def test_callback_exception_handling(self):
        """Test callback exceptions don't break execution."""
        mock_agent = Mock()
        mock_agent.start = Mock(return_value="Success")
        on_success = Mock(side_effect=Exception("Callback error"))
        
        scheduler = AgentScheduler(mock_agent, "Test task", on_success=on_success)
        
        # Should not raise exception even though callback fails
        result = scheduler.execute_once()
        assert result == "Success"


class TestAgentSchedulerThreading:
    """Test AgentScheduler threading functionality."""
    
    def test_thread_creation_on_start(self):
        """Test thread is created when start() is called."""
        mock_agent = Mock()
        scheduler = AgentScheduler(mock_agent, "Test task")
        
        scheduler.start("hourly", run_immediately=False)
        
        assert scheduler._thread is not None
        assert isinstance(scheduler._thread, threading.Thread)
        assert scheduler._thread.is_alive()
        
        scheduler.stop()
    
    def test_daemon_thread_flag(self):
        """Test thread is created as daemon."""
        mock_agent = Mock()
        scheduler = AgentScheduler(mock_agent, "Test task")
        
        scheduler.start("hourly", run_immediately=False)
        
        assert scheduler._thread.daemon == True
        
        scheduler.stop()
    
    def test_thread_cleanup_on_stop(self):
        """Test thread is cleaned up on stop()."""
        mock_agent = Mock()
        mock_agent.start = Mock(return_value="result")
        scheduler = AgentScheduler(mock_agent, "Test task")
        
        scheduler.start("*/1s", run_immediately=False)
        time.sleep(0.1)
        scheduler.stop()
        
        time.sleep(0.2)
        assert scheduler._thread.is_alive() == False
    
    def test_graceful_shutdown_timeout(self):
        """Test graceful shutdown with timeout."""
        mock_agent = Mock()
        mock_agent.start = Mock(return_value="result")
        scheduler = AgentScheduler(mock_agent, "Test task")
        
        scheduler.start("hourly", run_immediately=False)
        
        start_time = time.time()
        scheduler.stop()
        duration = time.time() - start_time
        
        # Should complete quickly (within timeout)
        assert duration < 11  # 10 second timeout + 1 second buffer


class TestAgentSchedulerIntervals:
    """Test AgentScheduler interval scheduling."""
    
    @patch('time.sleep')
    def test_run_immediately_true(self, mock_sleep):
        """Test run_immediately=True executes before schedule."""
        mock_agent = Mock()
        mock_agent.start = Mock(return_value="result")
        
        scheduler = AgentScheduler(mock_agent, "Test task")
        scheduler.start("hourly", run_immediately=True)
        
        time.sleep(0.1)
        scheduler.stop()
        
        # Should have executed at least once immediately
        assert scheduler._execution_count >= 1
    
    def test_run_immediately_false(self):
        """Test run_immediately=False waits for interval."""
        mock_agent = Mock()
        mock_agent.start = Mock(return_value="result")
        
        scheduler = AgentScheduler(mock_agent, "Test task")
        initial_count = scheduler._execution_count
        scheduler.start("hourly", run_immediately=False)
        
        time.sleep(0.05)  # Very short wait
        scheduler.stop()
        
        # Should not have executed yet (hourly interval) or at most started one execution
        assert scheduler._execution_count <= initial_count + 1
    
    def test_stop_event_interrupts_wait(self):
        """Test stop_event interrupts interval wait."""
        mock_agent = Mock()
        scheduler = AgentScheduler(mock_agent, "Test task")
        
        scheduler.start("hourly", run_immediately=False)
        
        start_time = time.time()
        scheduler.stop()
        duration = time.time() - start_time
        
        # Should stop quickly, not wait full hour
        assert duration < 2


class TestAgentSchedulerStatistics:
    """Test AgentScheduler statistics tracking."""
    
    def test_get_stats_initial_state(self):
        """Test get_stats() returns correct initial state."""
        mock_agent = Mock()
        scheduler = AgentScheduler(mock_agent, "Test task")
        
        stats = scheduler.get_stats()
        
        assert stats['is_running'] == False
        assert stats['total_executions'] == 0
        assert stats['successful_executions'] == 0
        assert stats['failed_executions'] == 0
        assert stats['success_rate'] == 0
    
    @patch('time.sleep')
    def test_execution_count_increment(self, mock_sleep):
        """Test execution count increments."""
        mock_agent = Mock()
        mock_agent.start = Mock(return_value="result")
        
        scheduler = AgentScheduler(mock_agent, "Test task")
        scheduler._execute_with_retry(max_retries=1)
        scheduler._execute_with_retry(max_retries=1)
        
        stats = scheduler.get_stats()
        assert stats['total_executions'] == 2
    
    @patch('time.sleep')
    def test_success_count_increment(self, mock_sleep):
        """Test success count increments."""
        mock_agent = Mock()
        mock_agent.start = Mock(return_value="result")
        
        scheduler = AgentScheduler(mock_agent, "Test task")
        scheduler._execute_with_retry(max_retries=1)
        
        stats = scheduler.get_stats()
        assert stats['successful_executions'] == 1
    
    @patch('time.sleep')
    def test_failure_count_increment(self, mock_sleep):
        """Test failure count increments."""
        mock_agent = Mock()
        mock_agent.start = Mock(side_effect=Exception("Error"))
        
        scheduler = AgentScheduler(mock_agent, "Test task")
        scheduler._execute_with_retry(max_retries=1)
        
        stats = scheduler.get_stats()
        assert stats['failed_executions'] == 1
    
    @patch('time.sleep')
    def test_success_rate_calculation(self, mock_sleep):
        """Test success rate is calculated correctly."""
        mock_agent = Mock()
        mock_agent.start = Mock(side_effect=[
            "success",
            Exception("fail"),
            "success"
        ])
        
        scheduler = AgentScheduler(mock_agent, "Test task")
        scheduler._execute_with_retry(max_retries=1)
        scheduler._execute_with_retry(max_retries=1)
        scheduler._execute_with_retry(max_retries=1)
        
        stats = scheduler.get_stats()
        assert stats['total_executions'] == 3
        assert stats['successful_executions'] == 2
        assert stats['failed_executions'] == 1
        assert stats['success_rate'] == pytest.approx(66.67, rel=0.1)
    
    def test_success_rate_with_zero_executions(self):
        """Test success rate with zero executions."""
        mock_agent = Mock()
        scheduler = AgentScheduler(mock_agent, "Test task")
        
        stats = scheduler.get_stats()
        assert stats['success_rate'] == 0


class TestCreateAgentScheduler:
    """Test create_agent_scheduler factory function."""
    
    def test_factory_creates_scheduler(self):
        """Test factory function creates AgentScheduler."""
        mock_agent = Mock()
        scheduler = create_agent_scheduler(mock_agent, "Test task")
        
        assert isinstance(scheduler, AgentScheduler)
        assert scheduler.agent == mock_agent
        assert scheduler.task == "Test task"
    
    def test_factory_with_config(self):
        """Test factory function with config."""
        mock_agent = Mock()
        config = {"key": "value"}
        scheduler = create_agent_scheduler(mock_agent, "Test task", config=config)
        
        assert scheduler.config == config
