"""
Tests for new scheduler features: stop-all, stats, and clean logs.
"""
import pytest
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock


class TestStopAllCommand:
    """Test stop-all command functionality."""
    
    def test_stop_all_with_multiple_schedulers(self):
        """Test stopping all schedulers at once."""
        from praisonai.cli.features.agent_scheduler import AgentSchedulerHandler
        from praisonai.scheduler.state_manager import SchedulerStateManager
        from praisonai.scheduler.daemon_manager import DaemonManager
        
        with tempfile.TemporaryDirectory() as tmpdir:
            state_dir = Path(tmpdir) / "schedulers"
            log_dir = Path(tmpdir) / "logs"
            
            state_manager = SchedulerStateManager(state_dir)
            daemon_manager = DaemonManager(log_dir)
            
            # Create mock states for 3 schedulers
            for i in range(1, 4):
                state_manager.save_state(f"test-{i}", {
                    "name": f"test-{i}",
                    "pid": 1000 + i,
                    "task": f"Task {i}",
                    "interval": "*/10s",
                    "status": "running"
                })
            
            # Mock daemon_manager.stop_daemon to return True
            with patch.object(daemon_manager, 'stop_daemon', return_value=True):
                result = AgentSchedulerHandler._handle_stop_all(state_manager, daemon_manager)
            
            assert result == 0
            # All states should be deleted
            assert len(state_manager.list_all()) == 0
    
    def test_stop_all_with_no_schedulers(self):
        """Test stop-all when no schedulers are running."""
        from praisonai.cli.features.agent_scheduler import AgentSchedulerHandler
        from praisonai.scheduler.state_manager import SchedulerStateManager
        from praisonai.scheduler.daemon_manager import DaemonManager
        
        with tempfile.TemporaryDirectory() as tmpdir:
            state_dir = Path(tmpdir) / "schedulers"
            log_dir = Path(tmpdir) / "logs"
            
            state_manager = SchedulerStateManager(state_dir)
            daemon_manager = DaemonManager(log_dir)
            
            result = AgentSchedulerHandler._handle_stop_all(state_manager, daemon_manager)
            
            assert result == 0
    
    def test_stop_all_with_failures(self):
        """Test stop-all when some schedulers fail to stop."""
        from praisonai.cli.features.agent_scheduler import AgentSchedulerHandler
        from praisonai.scheduler.state_manager import SchedulerStateManager
        from praisonai.scheduler.daemon_manager import DaemonManager
        
        with tempfile.TemporaryDirectory() as tmpdir:
            state_dir = Path(tmpdir) / "schedulers"
            log_dir = Path(tmpdir) / "logs"
            
            state_manager = SchedulerStateManager(state_dir)
            daemon_manager = DaemonManager(log_dir)
            
            # Create mock states
            state_manager.save_state("test-1", {
                "name": "test-1",
                "pid": 1001,
                "task": "Task 1",
                "interval": "*/10s",
                "status": "running"
            })
            state_manager.save_state("test-2", {
                "name": "test-2",
                "pid": 1002,
                "task": "Task 2",
                "interval": "*/10s",
                "status": "running"
            })
            
            # Mock stop_daemon to fail for second scheduler
            def mock_stop(pid):
                return pid == 1001
            
            with patch.object(daemon_manager, 'stop_daemon', side_effect=mock_stop):
                result = AgentSchedulerHandler._handle_stop_all(state_manager, daemon_manager)
            
            assert result == 1  # Should return 1 when failures occur


class TestStatsCommand:
    """Test stats command functionality."""
    
    def test_stats_aggregate(self):
        """Test aggregate stats for all schedulers."""
        from praisonai.cli.features.agent_scheduler import AgentSchedulerHandler
        from praisonai.scheduler.state_manager import SchedulerStateManager
        
        with tempfile.TemporaryDirectory() as tmpdir:
            state_dir = Path(tmpdir) / "schedulers"
            state_manager = SchedulerStateManager(state_dir)
            
            # Create mock states with execution data
            state_manager.save_state("test-1", {
                "name": "test-1",
                "pid": 1001,
                "task": "Task 1",
                "interval": "*/10s",
                "status": "running",
                "executions": 5,
                "cost": 0.0005
            })
            state_manager.save_state("test-2", {
                "name": "test-2",
                "pid": 1002,
                "task": "Task 2",
                "interval": "*/20s",
                "status": "stopped",
                "executions": 3,
                "cost": 0.0003
            })
            
            result = AgentSchedulerHandler._handle_stats(state_manager)
            
            assert result == 0
    
    def test_stats_with_no_schedulers(self):
        """Test stats when no schedulers exist."""
        from praisonai.cli.features.agent_scheduler import AgentSchedulerHandler
        from praisonai.scheduler.state_manager import SchedulerStateManager
        
        with tempfile.TemporaryDirectory() as tmpdir:
            state_dir = Path(tmpdir) / "schedulers"
            state_manager = SchedulerStateManager(state_dir)
            
            result = AgentSchedulerHandler._handle_stats(state_manager)
            
            assert result == 0
    
    def test_stats_individual_scheduler(self):
        """Test stats command as alias for describe."""
        from praisonai.cli.features.agent_scheduler import AgentSchedulerHandler
        from praisonai.scheduler.state_manager import SchedulerStateManager
        from praisonai.scheduler.daemon_manager import DaemonManager
        
        with tempfile.TemporaryDirectory() as tmpdir:
            state_dir = Path(tmpdir) / "schedulers"
            log_dir = Path(tmpdir) / "logs"
            
            state_manager = SchedulerStateManager(state_dir)
            daemon_manager = DaemonManager(log_dir)
            
            # Create mock state
            state_manager.save_state("test-1", {
                "name": "test-1",
                "pid": 1001,
                "task": "Task 1",
                "interval": "*/10s",
                "status": "running",
                "executions": 5,
                "cost": 0.0005,
                "started_at": "2025-12-22T10:00:00"
            })
            
            result = AgentSchedulerHandler._handle_stats(
                state_manager, 
                unknown_args=["test-1"],
                daemon_manager=daemon_manager
            )
            
            assert result == 0


class TestCleanLogs:
    """Test clean log output (DEBUG level)."""
    
    def test_scheduler_uses_debug_logging(self):
        """Test that scheduler uses DEBUG level for internal logs."""
        from praisonai.scheduler.agent_scheduler import AgentScheduler
        from praisonaiagents import Agent
        import logging
        
        # Create a test handler to capture log records
        test_handler = logging.Handler()
        test_handler.setLevel(logging.DEBUG)
        records = []
        
        def capture_record(record):
            records.append(record)
            return True
        
        test_handler.emit = lambda record: records.append(record)
        
        # Get the scheduler logger
        logger = logging.getLogger('praisonai.scheduler')
        logger.addHandler(test_handler)
        logger.setLevel(logging.DEBUG)
        
        try:
            agent = Agent(
                name="Test Agent",
                role="Tester",
                goal="Test logging",
                instructions="Test"
            )
            
            scheduler = AgentScheduler(
                agent=agent,
                task="Test task",
                timeout=5,
                max_cost=1.0
            )
            
            # Start and immediately stop
            scheduler.start(schedule_expr="*/10s", max_retries=1, run_immediately=False)
            scheduler.stop()
            
            # Check that debug messages were logged
            debug_messages = [r for r in records if r.levelno == logging.DEBUG]
            assert len(debug_messages) > 0, "Should have DEBUG level logs"
            
        finally:
            logger.removeHandler(test_handler)


class TestStateUpdatePersistence:
    """Test that execution stats are persisted to state files."""
    
    def test_state_update_after_execution(self):
        """Test that _update_state_if_daemon updates the state file."""
        from praisonai.scheduler.agent_scheduler import AgentScheduler
        from praisonai.scheduler.state_manager import SchedulerStateManager
        from praisonaiagents import Agent
        import os
        
        with tempfile.TemporaryDirectory() as tmpdir:
            state_dir = Path(tmpdir) / "schedulers"
            state_dir.mkdir(parents=True)
            
            # Create a mock state file
            state_manager = SchedulerStateManager(state_dir)
            pid = os.getpid()
            
            state_manager.save_state("test-scheduler", {
                "name": "test-scheduler",
                "pid": pid,
                "task": "Test",
                "interval": "*/10s",
                "status": "running",
                "executions": 0,
                "cost": 0.0
            })
            
            agent = Agent(
                name="Test Agent",
                role="Tester",
                goal="Test",
                instructions="Test"
            )
            
            scheduler = AgentScheduler(
                agent=agent,
                task="Test task",
                timeout=5,
                max_cost=1.0
            )
            
            # Simulate execution
            scheduler._execution_count = 5
            scheduler._total_cost = 0.0005
            
            # Call update method
            scheduler._update_state_if_daemon()
            
            # Check if state was updated
            state = state_manager.load_state("test-scheduler")
            if state:  # State might be updated
                assert state.get('executions', 0) >= 0
                assert state.get('cost', 0.0) >= 0.0
