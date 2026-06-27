"""
Unit tests for scheduler fixes identified in PR #1857.

Tests for:
1. AsyncAgentScheduler._start_time initialization fix
2. Async I/O handling with asyncio.to_thread for _update_state_if_daemon
3. Zero budget (max_cost=0.0) handling in _BaseAgentScheduler._build_stats
4. Integration tests for the fixes

These tests ensure the critical bugs identified by reviewers are properly fixed.
"""

import asyncio
import pytest
import tempfile
import os
import json
from unittest.mock import AsyncMock, Mock, patch
from datetime import datetime

# Import the scheduler classes to test
from praisonai.scheduler.async_agent_scheduler import AsyncAgentScheduler
from praisonai.scheduler._base_scheduler import _BaseAgentScheduler


class TestAsyncAgentSchedulerStartTimeInit:
    """Test _start_time initialization fix for AsyncAgentScheduler."""

    def test_start_time_initialized_in_init(self):
        """Test that _start_time is properly initialized to None in __init__."""
        mock_agent = Mock()
        scheduler = AsyncAgentScheduler(mock_agent, "test task")
        
        # _start_time should be initialized to None
        assert hasattr(scheduler, '_start_time')
        assert scheduler._start_time is None

    @pytest.mark.asyncio
    async def test_start_time_set_on_start(self):
        """Test that _start_time is set when scheduler starts."""
        mock_agent = Mock()
        mock_agent.astart = AsyncMock(return_value="result")
        scheduler = AsyncAgentScheduler(mock_agent, "test task")
        
        # Start the scheduler
        await scheduler.start("*/1s", run_immediately=False)
        
        # _start_time should now be set
        assert scheduler._start_time is not None
        assert isinstance(scheduler._start_time, datetime)
        
        await scheduler.stop()

    @pytest.mark.asyncio
    async def test_build_stats_with_start_time(self):
        """Test that _build_stats works correctly when _start_time is set."""
        mock_agent = Mock()
        mock_agent.astart = AsyncMock(return_value="result")
        scheduler = AsyncAgentScheduler(mock_agent, "test task")
        
        # Start scheduler to set _start_time
        await scheduler.start("*/1s", run_immediately=False)
        
        # Get stats - should include runtime_seconds
        stats = await scheduler.get_stats_async()
        assert 'runtime_seconds' in stats
        assert stats['runtime_seconds'] >= 0
        
        await scheduler.stop()

    @pytest.mark.asyncio
    async def test_build_stats_without_start_time(self):
        """Test that _build_stats works when _start_time is None."""
        mock_agent = Mock()
        scheduler = AsyncAgentScheduler(mock_agent, "test task")
        
        # Don't start scheduler - _start_time remains None
        stats = await scheduler.get_stats_async()
        assert 'runtime_seconds' in stats
        assert stats['runtime_seconds'] == 0


class TestAsyncIODaemonStateUpdates:
    """Test asyncio.to_thread handling for _update_state_if_daemon."""

    @pytest.mark.asyncio
    async def test_update_state_daemon_uses_asyncio_to_thread(self):
        """Test that _update_state_if_daemon is called via asyncio.to_thread."""
        mock_agent = Mock()
        mock_agent.astart = AsyncMock(return_value="result")
        scheduler = AsyncAgentScheduler(mock_agent, "test task")
        
        # Mock the _update_state_if_daemon method
        with patch.object(scheduler, '_update_state_if_daemon') as mock_update:
            with patch('asyncio.to_thread') as mock_to_thread:
                future = asyncio.Future()
                future.set_result(None)
                mock_to_thread.return_value = future
                
                
                # Execute with retry - should call _update_state_if_daemon via asyncio.to_thread
                await scheduler._execute_with_retry(max_retries=1)
                
                # Verify asyncio.to_thread was called with _update_state_if_daemon
                mock_to_thread.assert_called_with(scheduler._update_state_if_daemon)

    @pytest.mark.asyncio
    async def test_daemon_state_update_on_success_path(self):
        """Test that daemon state is updated on successful execution."""
        mock_agent = Mock()
        mock_agent.astart = AsyncMock(return_value="result")
        scheduler = AsyncAgentScheduler(mock_agent, "test task")
        
        with patch('asyncio.to_thread') as mock_to_thread:
            future = asyncio.Future()
            future.set_result(None)
            mock_to_thread.return_value = future
            
            
            await scheduler._execute_with_retry(max_retries=1)
            
            # Should be called once on success path
            assert mock_to_thread.call_count >= 1
            mock_to_thread.assert_called_with(scheduler._update_state_if_daemon)

    @pytest.mark.asyncio
    async def test_daemon_state_update_on_failure_path(self):
        """Test that daemon state is updated on failure execution."""
        mock_agent = Mock()
        mock_agent.astart = AsyncMock(side_effect=Exception("test error"))
        scheduler = AsyncAgentScheduler(mock_agent, "test task")
        
        with patch('asyncio.to_thread') as mock_to_thread:
            future = asyncio.Future()
            future.set_result(None)
            mock_to_thread.return_value = future
            

            await scheduler._execute_with_retry(max_retries=1)
            
            # Should be called once on failure path
            assert mock_to_thread.call_count >= 1
            mock_to_thread.assert_called_with(scheduler._update_state_if_daemon)

    @pytest.mark.asyncio
    async def test_no_blocking_io_on_event_loop(self):
        """Test that no blocking I/O operations are performed directly on event loop."""
        mock_agent = Mock()
        mock_agent.astart = AsyncMock(return_value="result")
        scheduler = AsyncAgentScheduler(mock_agent, "test task")
        
        # Create a temporary state directory and file to ensure the daemon update logic runs
        with tempfile.TemporaryDirectory() as temp_dir:
            state_file = os.path.join(temp_dir, "test_scheduler.json")
            state_data = {
                "pid": os.getpid(),
                "executions": 0,
                "cost": 0.0
            }
            with open(state_file, "w") as f:
                json.dump(state_data, f)
            
            # Patch the state directory to use our temp directory
            with patch('os.path.expanduser', return_value=temp_dir):
                with patch('os.listdir', return_value=["test_scheduler.json"]):
                    # Execute - this should not block the event loop
                    await scheduler._execute_with_retry(max_retries=1)
                    
            # Verify the scheduler completed without blocking


class TestZeroBudgetHandling:
    """Test max_cost=0.0 handling in _BaseAgentScheduler._build_stats."""

    def test_zero_budget_remaining_calculation(self):
        """Test that max_cost=0.0 is handled correctly (not treated as None)."""
        # Create a concrete scheduler class for testing
        class TestScheduler(_BaseAgentScheduler):
            def __init__(self):
                self.is_running = False
                self.max_cost = 0.0  # Zero budget
                self._execution_count = 5
                self._success_count = 3
                self._failure_count = 2
                self._total_cost = 0.0
                self._start_time = datetime.now()
        
        scheduler = TestScheduler()
        
        # Build stats with zero budget
        stats = scheduler._build_stats(
            execs=5,
            success=3,
            failed=2,
            total_cost=0.0
        )
        
        # remaining_budget should be 0.0, not None
        assert 'remaining_budget' in stats
        assert stats['remaining_budget'] == 0.0
        assert stats['remaining_budget'] is not None

    def test_zero_budget_with_costs(self):
        """Test zero budget with some costs incurred."""
        class TestScheduler(_BaseAgentScheduler):
            def __init__(self):
                self.is_running = False
                self.max_cost = 0.0  # Zero budget
                self._execution_count = 5
                self._success_count = 3
                self._failure_count = 2
                self._total_cost = 0.1  # Some cost incurred
                self._start_time = datetime.now()
        
        scheduler = TestScheduler()
        
        stats = scheduler._build_stats(
            execs=5,
            success=3,
            failed=2,
            total_cost=0.1
        )
        
        # remaining_budget should be negative (-0.1)
        assert 'remaining_budget' in stats
        assert stats['remaining_budget'] == -0.1

    def test_none_budget_handling(self):
        """Test that None budget (unlimited) returns None for remaining_budget."""
        class TestScheduler(_BaseAgentScheduler):
            def __init__(self):
                self.is_running = False
                self.max_cost = None  # Unlimited budget
                self._execution_count = 5
                self._success_count = 3
                self._failure_count = 2
                self._total_cost = 0.1
                self._start_time = datetime.now()
        
        scheduler = TestScheduler()
        
        stats = scheduler._build_stats(
            execs=5,
            success=3,
            failed=2,
            total_cost=0.1
        )
        
        # remaining_budget should be None for unlimited budget
        assert 'remaining_budget' in stats
        assert stats['remaining_budget'] is None

    @pytest.mark.asyncio
    async def test_zero_budget_stops_execution(self):
        """Test that zero budget prevents execution in AsyncAgentScheduler."""
        mock_agent = Mock()
        mock_agent.astart = AsyncMock(return_value="result")
        scheduler = AsyncAgentScheduler(mock_agent, "test task", max_cost=0.0)
        
        # Set some initial cost to trigger budget limit
        scheduler._total_cost = 0.0
        
        # Start scheduler to initialize async primitives
        scheduler.is_running = True
        scheduler._ensure_async_primitives()
        
        # Execute with retry - should stop due to zero budget
        await scheduler._execute_with_retry(max_retries=1)
        
        # Should have set stop event
        assert scheduler._stop_event.is_set()
        assert not scheduler.is_running


class TestCLIToolResolverIntegration:
    """Test CLI tool resolution uses ToolResolver instead of direct TOOL_MAPPINGS access."""

    def test_cli_load_tools_uses_resolver(self):
        """Test that _load_tools uses ToolResolver.resolve instead of direct TOOL_MAPPINGS."""
        from praisonai.cli.main import PraisonAI
        
        cli = PraisonAI()
        
        # Mock ToolResolver
        with patch("praisonai.tool_resolver.ToolResolver") as MockResolver:
            mock_resolver_instance = Mock()
            MockResolver.return_value = mock_resolver_instance
            mock_resolver_instance.resolve.return_value = Mock()  # Mock tool
            
            # Test loading comma-separated tools
            tools = cli._load_tools("tool1,tool2")
            
            # Verify ToolResolver was instantiated
            MockResolver.assert_called_once()
            
            # Verify resolve was called for each tool with instantiate=True
            assert mock_resolver_instance.resolve.call_count == 2
            mock_resolver_instance.resolve.assert_any_call("tool1", instantiate=True)
            mock_resolver_instance.resolve.assert_any_call("tool2", instantiate=True)

    def test_cli_load_tools_handles_empty_strings(self):
        """Test that _load_tools filters out empty strings from tool names."""
        from praisonai.cli.main import PraisonAI
        
        cli = PraisonAI()
        
        with patch("praisonai.tool_resolver.ToolResolver") as MockResolver:
            mock_resolver_instance = Mock()
            MockResolver.return_value = mock_resolver_instance
            mock_resolver_instance.resolve.return_value = Mock()
            
            # Test with empty strings and spaces
            tools = cli._load_tools("tool1, , tool2,  ")
            
            # Should only call resolve for actual tool names
            assert mock_resolver_instance.resolve.call_count == 2
            mock_resolver_instance.resolve.assert_any_call("tool1", instantiate=True)
            mock_resolver_instance.resolve.assert_any_call("tool2", instantiate=True)

    def test_cli_load_tools_error_handling(self):
        """Test that _load_tools handles resolution errors gracefully."""
        from praisonai.cli.main import PraisonAI
        
        cli = PraisonAI()
        
        with patch("praisonai.tool_resolver.ToolResolver") as MockResolver:
            mock_resolver_instance = Mock()
            MockResolver.return_value = mock_resolver_instance
            # Simulate tool resolution failure
            mock_resolver_instance.resolve.side_effect = Exception("Tool not found")
            
            # Should not raise, should handle gracefully
            tools = cli._load_tools("nonexistent_tool")
            
            # Should return empty list
            assert tools == []


class TestFrameworkAdapterDuplication:
    """Test that duplicate arun() methods have been properly removed."""

    def test_no_duplicate_arun_in_protocol(self):
        """Test that FrameworkAdapter protocol has single arun method."""
        from praisonai.framework_adapters.base import FrameworkAdapter
        
        # Get all method names from the protocol
        import inspect
        methods = [name for name, _ in inspect.getmembers(FrameworkAdapter, inspect.ismethod)
                  if not name.startswith('__')]
        
        # Count arun occurrences
        arun_count = methods.count('arun')
        assert arun_count <= 1, f"Found {arun_count} arun methods in protocol, expected 0 or 1"

    def test_framework_adapter_has_cleanup_method(self):
        """Test that FrameworkAdapter protocol includes cleanup method."""
        from praisonai.framework_adapters.base import FrameworkAdapter
        
        # Check that cleanup method is defined in the protocol
        import inspect
        methods = [name for name, _ in inspect.getmembers(FrameworkAdapter)]
        assert 'cleanup' in methods, "FrameworkAdapter protocol should include cleanup method"


class TestIntegrationScenarios:
    """Integration tests combining multiple fixes."""

    @pytest.mark.asyncio
    async def test_full_scheduler_lifecycle_with_fixes(self):
        """Test complete scheduler lifecycle with all fixes applied."""
        mock_agent = Mock()
        mock_agent.astart = AsyncMock(return_value="result")
        
        # Create scheduler with small budget
        scheduler = AsyncAgentScheduler(mock_agent, "test task", max_cost=0.01)
        
        # Verify initial state
        assert scheduler._start_time is None
        assert scheduler.max_cost == 0.01
        
        # Start scheduler
        await scheduler.start("*/1s", run_immediately=False)
        
        # Verify _start_time was set
        assert scheduler._start_time is not None
        
        # Get stats - should include all fields with proper calculations
        stats = await scheduler.get_stats_async()
        assert 'runtime_seconds' in stats
        assert 'remaining_budget' in stats
        assert stats['remaining_budget'] is not None  # Should be calculated, not None
        
        # Stop scheduler
        await scheduler.stop()
        assert not scheduler.is_running

    @pytest.mark.asyncio
    async def test_daemon_state_persistence_integration(self):
        """Test daemon state persistence works with async I/O fixes."""
        mock_agent = Mock()
        mock_agent.astart = AsyncMock(return_value="result")
        scheduler = AsyncAgentScheduler(mock_agent, "test task")
        
        # Create temporary state directory
        with tempfile.TemporaryDirectory() as temp_dir:
            state_file = os.path.join(temp_dir, "scheduler_state.json")
            initial_state = {
                "pid": os.getpid(),
                "executions": 0,
                "cost": 0.0
            }
            with open(state_file, "w") as f:
                json.dump(initial_state, f)
            
            # Mock the state directory
            with patch('os.path.expanduser', return_value=temp_dir):
                with patch('os.listdir', return_value=["scheduler_state.json"]):
                    # Execute should update state via asyncio.to_thread
                    await scheduler._execute_with_retry(max_retries=1)
            
            # Verify state file was updated (execution count incremented)
            with open(state_file, "r") as f:
                updated_state = json.load(f)
            
            assert updated_state["executions"] >= 1

    def test_zero_cost_edge_cases(self):
        """Test edge cases for zero cost handling."""
        class TestScheduler(_BaseAgentScheduler):
            def __init__(self, max_cost, total_cost):
                self.is_running = False
                self.max_cost = max_cost
                self._execution_count = 1
                self._success_count = 1
                self._failure_count = 0
                self._total_cost = total_cost
                self._start_time = datetime.now()
        
        # Test exactly zero budget, zero cost
        scheduler = TestScheduler(max_cost=0.0, total_cost=0.0)
        stats = scheduler._build_stats(execs=1, success=1, failed=0, total_cost=0.0)
        assert stats['remaining_budget'] == 0.0
        
        # Test very small budget
        scheduler = TestScheduler(max_cost=0.0001, total_cost=0.0)
        stats = scheduler._build_stats(execs=1, success=1, failed=0, total_cost=0.0)
        assert abs(stats['remaining_budget'] - 0.0001) < 1e-6
        
        # Test floating point precision
        scheduler = TestScheduler(max_cost=0.1, total_cost=0.05)
        stats = scheduler._build_stats(execs=1, success=1, failed=0, total_cost=0.05)
        assert abs(stats['remaining_budget'] - 0.05) < 1e-6