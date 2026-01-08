"""Tests for Queue Persistence Layer."""

import pytest
import tempfile
import os
from praisonai.cli.features.queue.models import QueuedRun, RunState, RunPriority
from praisonai.cli.features.queue.persistence import QueuePersistence


class TestQueuePersistence:
    """Tests for QueuePersistence."""
    
    @pytest.fixture
    def db_path(self):
        """Create temporary database path."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield os.path.join(tmpdir, "test_queue.db")
    
    @pytest.fixture
    def persistence(self, db_path):
        """Create test persistence instance."""
        p = QueuePersistence(db_path)
        p.initialize()
        yield p
        p.close()
    
    def test_initialize_creates_tables(self, persistence):
        """Test initialization creates tables."""
        # Should not raise
        persistence.initialize()
    
    def test_save_and_load_run(self, persistence):
        """Test saving and loading a run."""
        run = QueuedRun(
            run_id="test123",
            agent_name="TestAgent",
            input_content="Hello",
            state=RunState.QUEUED,
            priority=RunPriority.HIGH,
        )
        
        persistence.save_run(run)
        loaded = persistence.load_run("test123")
        
        assert loaded is not None
        assert loaded.run_id == "test123"
        assert loaded.agent_name == "TestAgent"
        assert loaded.input_content == "Hello"
        assert loaded.state == RunState.QUEUED
        assert loaded.priority == RunPriority.HIGH
    
    def test_load_nonexistent_run(self, persistence):
        """Test loading a nonexistent run."""
        loaded = persistence.load_run("nonexistent")
        assert loaded is None
    
    def test_update_run(self, persistence):
        """Test updating a run."""
        run = QueuedRun(run_id="test123", agent_name="TestAgent")
        persistence.save_run(run)
        
        run.state = RunState.RUNNING
        run.output_content = "Result"
        persistence.save_run(run)
        
        loaded = persistence.load_run("test123")
        assert loaded.state == RunState.RUNNING
        assert loaded.output_content == "Result"
    
    def test_list_runs(self, persistence):
        """Test listing runs."""
        for i in range(5):
            run = QueuedRun(
                run_id=f"run{i}",
                agent_name="TestAgent",
                priority=RunPriority.NORMAL if i % 2 == 0 else RunPriority.HIGH,
            )
            persistence.save_run(run)
        
        runs = persistence.list_runs(limit=10)
        assert len(runs) == 5
    
    def test_list_runs_filter_by_state(self, persistence):
        """Test filtering runs by state."""
        run1 = QueuedRun(run_id="run1", agent_name="Agent", state=RunState.QUEUED)
        run2 = QueuedRun(run_id="run2", agent_name="Agent", state=RunState.RUNNING)
        run3 = QueuedRun(run_id="run3", agent_name="Agent", state=RunState.QUEUED)
        
        persistence.save_run(run1)
        persistence.save_run(run2)
        persistence.save_run(run3)
        
        queued = persistence.list_runs(state=RunState.QUEUED)
        assert len(queued) == 2
        
        running = persistence.list_runs(state=RunState.RUNNING)
        assert len(running) == 1
    
    def test_list_runs_filter_by_session(self, persistence):
        """Test filtering runs by session."""
        run1 = QueuedRun(run_id="run1", agent_name="Agent", session_id="session1")
        run2 = QueuedRun(run_id="run2", agent_name="Agent", session_id="session2")
        run3 = QueuedRun(run_id="run3", agent_name="Agent", session_id="session1")
        
        persistence.save_run(run1)
        persistence.save_run(run2)
        persistence.save_run(run3)
        
        session1_runs = persistence.list_runs(session_id="session1")
        assert len(session1_runs) == 2
    
    def test_delete_run(self, persistence):
        """Test deleting a run."""
        run = QueuedRun(run_id="test123", agent_name="TestAgent")
        persistence.save_run(run)
        
        result = persistence.delete_run("test123")
        assert result is True
        
        loaded = persistence.load_run("test123")
        assert loaded is None
    
    def test_delete_nonexistent_run(self, persistence):
        """Test deleting a nonexistent run."""
        result = persistence.delete_run("nonexistent")
        assert result is False
    
    def test_update_run_state(self, persistence):
        """Test updating run state."""
        run = QueuedRun(run_id="test123", agent_name="TestAgent")
        persistence.save_run(run)
        
        result = persistence.update_run_state(
            "test123",
            RunState.FAILED,
            error="Test error",
        )
        
        assert result is True
        
        loaded = persistence.load_run("test123")
        assert loaded.state == RunState.FAILED
        assert loaded.error == "Test error"
        assert loaded.ended_at is not None
    
    def test_load_pending_runs(self, persistence):
        """Test loading pending runs for crash recovery."""
        run1 = QueuedRun(run_id="run1", agent_name="Agent", state=RunState.QUEUED)
        run2 = QueuedRun(run_id="run2", agent_name="Agent", state=RunState.RUNNING)
        run3 = QueuedRun(run_id="run3", agent_name="Agent", state=RunState.SUCCEEDED)
        
        persistence.save_run(run1)
        persistence.save_run(run2)
        persistence.save_run(run3)
        
        pending = persistence.load_pending_runs()
        assert len(pending) == 2
        
        run_ids = [r.run_id for r in pending]
        assert "run1" in run_ids
        assert "run2" in run_ids
        assert "run3" not in run_ids
    
    def test_mark_interrupted_as_failed(self, persistence):
        """Test marking interrupted runs as failed."""
        run1 = QueuedRun(run_id="run1", agent_name="Agent", state=RunState.RUNNING)
        run2 = QueuedRun(run_id="run2", agent_name="Agent", state=RunState.RUNNING)
        run3 = QueuedRun(run_id="run3", agent_name="Agent", state=RunState.QUEUED)
        
        persistence.save_run(run1)
        persistence.save_run(run2)
        persistence.save_run(run3)
        
        count = persistence.mark_interrupted_as_failed()
        assert count == 2
        
        loaded1 = persistence.load_run("run1")
        assert loaded1.state == RunState.FAILED
        assert "Interrupted" in loaded1.error
    
    def test_get_stats(self, persistence):
        """Test getting queue statistics."""
        runs = [
            QueuedRun(run_id="run1", agent_name="Agent", state=RunState.QUEUED),
            QueuedRun(run_id="run2", agent_name="Agent", state=RunState.RUNNING),
            QueuedRun(run_id="run3", agent_name="Agent", state=RunState.SUCCEEDED),
            QueuedRun(run_id="run4", agent_name="Agent", state=RunState.FAILED),
        ]
        
        for run in runs:
            persistence.save_run(run)
        
        stats = persistence.get_stats()
        
        assert stats.queued_count == 1
        assert stats.running_count == 1
        assert stats.succeeded_count == 1
        assert stats.failed_count == 1
        assert stats.total_runs == 4
    
    def test_save_and_load_session(self, persistence):
        """Test saving and loading session."""
        persistence.save_session(
            session_id="session123",
            user_id="user456",
            state={"key": "value"},
            config={"model": "gpt-4"},
        )
        
        loaded = persistence.load_session("session123")
        
        assert loaded is not None
        assert loaded["session_id"] == "session123"
        assert loaded["user_id"] == "user456"
        assert loaded["state"] == {"key": "value"}
        assert loaded["config"] == {"model": "gpt-4"}
    
    def test_list_sessions(self, persistence):
        """Test listing sessions."""
        for i in range(3):
            persistence.save_session(f"session{i}")
        
        sessions = persistence.list_sessions()
        assert len(sessions) == 3
    
    def test_cleanup_old_runs(self, persistence):
        """Test cleaning up old runs."""
        import time
        
        # Create old run
        old_run = QueuedRun(
            run_id="old_run",
            agent_name="Agent",
            state=RunState.SUCCEEDED,
        )
        old_run.created_at = time.time() - (40 * 24 * 60 * 60)  # 40 days ago
        persistence.save_run(old_run)
        
        # Create recent run
        recent_run = QueuedRun(
            run_id="recent_run",
            agent_name="Agent",
            state=RunState.SUCCEEDED,
        )
        persistence.save_run(recent_run)
        
        count = persistence.cleanup_old_runs(days=30)
        assert count == 1
        
        assert persistence.load_run("old_run") is None
        assert persistence.load_run("recent_run") is not None
