"""
TDD: Tests for scheduler state manager (persistent storage).
"""
import pytest
import json
import tempfile
import os
from pathlib import Path
from datetime import datetime


class TestSchedulerStateManager:
    """Test scheduler state persistence."""
    
    def test_create_state_directory(self):
        """Test that state directory is created if it doesn't exist."""
        from praisonai.scheduler.state_manager import SchedulerStateManager
        
        with tempfile.TemporaryDirectory() as tmpdir:
            state_dir = Path(tmpdir) / ".praisonai" / "schedulers"
            manager = SchedulerStateManager(state_dir=state_dir)
            
            assert state_dir.exists()
            assert state_dir.is_dir()
    
    def test_save_scheduler_state(self):
        """Test saving scheduler state to JSON."""
        from praisonai.scheduler.state_manager import SchedulerStateManager
        
        with tempfile.TemporaryDirectory() as tmpdir:
            state_dir = Path(tmpdir) / ".praisonai" / "schedulers"
            manager = SchedulerStateManager(state_dir=state_dir)
            
            state = {
                "name": "test-scheduler",
                "pid": 12345,
                "task": "Test task",
                "interval": "hourly",
                "status": "running",
                "started_at": datetime.now().isoformat(),
                "executions": 0,
                "cost": 0.0
            }
            
            manager.save_state("test-scheduler", state)
            
            state_file = state_dir / "test-scheduler.json"
            assert state_file.exists()
            
            with open(state_file) as f:
                saved_state = json.load(f)
            
            assert saved_state["name"] == "test-scheduler"
            assert saved_state["pid"] == 12345
    
    def test_load_scheduler_state(self):
        """Test loading scheduler state from JSON."""
        from praisonai.scheduler.state_manager import SchedulerStateManager
        
        with tempfile.TemporaryDirectory() as tmpdir:
            state_dir = Path(tmpdir) / ".praisonai" / "schedulers"
            manager = SchedulerStateManager(state_dir=state_dir)
            
            # Save state first
            state = {
                "name": "test-scheduler",
                "pid": 12345,
                "task": "Test task"
            }
            manager.save_state("test-scheduler", state)
            
            # Load it back
            loaded_state = manager.load_state("test-scheduler")
            
            assert loaded_state is not None
            assert loaded_state["name"] == "test-scheduler"
            assert loaded_state["pid"] == 12345
    
    def test_load_nonexistent_state(self):
        """Test loading state that doesn't exist returns None."""
        from praisonai.scheduler.state_manager import SchedulerStateManager
        
        with tempfile.TemporaryDirectory() as tmpdir:
            state_dir = Path(tmpdir) / ".praisonai" / "schedulers"
            manager = SchedulerStateManager(state_dir=state_dir)
            
            loaded_state = manager.load_state("nonexistent")
            
            assert loaded_state is None
    
    def test_list_all_schedulers(self):
        """Test listing all scheduler states."""
        from praisonai.scheduler.state_manager import SchedulerStateManager
        
        with tempfile.TemporaryDirectory() as tmpdir:
            state_dir = Path(tmpdir) / ".praisonai" / "schedulers"
            manager = SchedulerStateManager(state_dir=state_dir)
            
            # Save multiple states
            for i in range(3):
                state = {
                    "name": f"scheduler-{i}",
                    "pid": 10000 + i,
                    "task": f"Task {i}"
                }
                manager.save_state(f"scheduler-{i}", state)
            
            all_states = manager.list_all()
            
            assert len(all_states) == 3
            assert all(s["name"].startswith("scheduler-") for s in all_states)
    
    def test_delete_scheduler_state(self):
        """Test deleting scheduler state."""
        from praisonai.scheduler.state_manager import SchedulerStateManager
        
        with tempfile.TemporaryDirectory() as tmpdir:
            state_dir = Path(tmpdir) / ".praisonai" / "schedulers"
            manager = SchedulerStateManager(state_dir=state_dir)
            
            # Save state
            state = {"name": "test-scheduler", "pid": 12345}
            manager.save_state("test-scheduler", state)
            
            # Delete it
            manager.delete_state("test-scheduler")
            
            # Verify it's gone
            loaded_state = manager.load_state("test-scheduler")
            assert loaded_state is None
    
    def test_update_scheduler_state(self):
        """Test updating existing scheduler state."""
        from praisonai.scheduler.state_manager import SchedulerStateManager
        
        with tempfile.TemporaryDirectory() as tmpdir:
            state_dir = Path(tmpdir) / ".praisonai" / "schedulers"
            manager = SchedulerStateManager(state_dir=state_dir)
            
            # Save initial state
            state = {
                "name": "test-scheduler",
                "pid": 12345,
                "executions": 0
            }
            manager.save_state("test-scheduler", state)
            
            # Update state
            state["executions"] = 5
            manager.save_state("test-scheduler", state)
            
            # Load and verify
            loaded_state = manager.load_state("test-scheduler")
            assert loaded_state["executions"] == 5
    
    def test_generate_unique_name(self):
        """Test generating unique scheduler names."""
        from praisonai.scheduler.state_manager import SchedulerStateManager
        
        with tempfile.TemporaryDirectory() as tmpdir:
            state_dir = Path(tmpdir) / ".praisonai" / "schedulers"
            manager = SchedulerStateManager(state_dir=state_dir)
            
            # Save a scheduler
            state = {"name": "scheduler-0", "pid": 12345}
            manager.save_state("scheduler-0", state)
            
            # Generate unique name
            unique_name = manager.generate_unique_name("scheduler")
            
            assert unique_name != "scheduler-0"
            assert unique_name.startswith("scheduler-")
    
    def test_check_process_alive(self):
        """Test checking if process is still alive."""
        from praisonai.scheduler.state_manager import SchedulerStateManager
        import os
        
        with tempfile.TemporaryDirectory() as tmpdir:
            state_dir = Path(tmpdir) / ".praisonai" / "schedulers"
            manager = SchedulerStateManager(state_dir=state_dir)
            
            # Current process should be alive
            current_pid = os.getpid()
            assert manager.is_process_alive(current_pid) is True
            
            # Non-existent process should be dead
            assert manager.is_process_alive(999999) is False


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
