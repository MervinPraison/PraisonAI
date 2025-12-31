"""Tests for Queue System Data Models."""

import pytest
import time
from praisonai.cli.features.queue.models import (
    QueuedRun,
    RunState,
    RunPriority,
    QueueConfig,
    QueueStats,
    StreamChunk,
    QueueEvent,
)


class TestRunState:
    """Tests for RunState enum."""
    
    def test_terminal_states(self):
        """Test terminal state detection."""
        assert RunState.SUCCEEDED.is_terminal()
        assert RunState.FAILED.is_terminal()
        assert RunState.CANCELLED.is_terminal()
        assert not RunState.QUEUED.is_terminal()
        assert not RunState.RUNNING.is_terminal()
        assert not RunState.PAUSED.is_terminal()
    
    def test_active_states(self):
        """Test active state detection."""
        assert RunState.QUEUED.is_active()
        assert RunState.RUNNING.is_active()
        assert RunState.PAUSED.is_active()
        assert not RunState.SUCCEEDED.is_active()
        assert not RunState.FAILED.is_active()


class TestRunPriority:
    """Tests for RunPriority enum."""
    
    def test_priority_ordering(self):
        """Test priority ordering."""
        assert RunPriority.URGENT > RunPriority.HIGH
        assert RunPriority.HIGH > RunPriority.NORMAL
        assert RunPriority.NORMAL > RunPriority.LOW
    
    def test_from_string(self):
        """Test parsing from string."""
        assert RunPriority.from_string("low") == RunPriority.LOW
        assert RunPriority.from_string("NORMAL") == RunPriority.NORMAL
        assert RunPriority.from_string("High") == RunPriority.HIGH
        assert RunPriority.from_string("urgent") == RunPriority.URGENT
        assert RunPriority.from_string("invalid") == RunPriority.NORMAL


class TestQueuedRun:
    """Tests for QueuedRun dataclass."""
    
    def test_default_values(self):
        """Test default values."""
        run = QueuedRun()
        assert run.run_id  # Auto-generated
        assert run.agent_name == ""
        assert run.state == RunState.QUEUED
        assert run.priority == RunPriority.NORMAL
        assert run.retry_count == 0
        assert run.max_retries == 3
    
    def test_custom_values(self):
        """Test custom values."""
        run = QueuedRun(
            run_id="test123",
            agent_name="TestAgent",
            input_content="Hello",
            state=RunState.RUNNING,
            priority=RunPriority.HIGH,
        )
        assert run.run_id == "test123"
        assert run.agent_name == "TestAgent"
        assert run.input_content == "Hello"
        assert run.state == RunState.RUNNING
        assert run.priority == RunPriority.HIGH
    
    def test_duration_calculation(self):
        """Test duration calculation."""
        run = QueuedRun()
        assert run.duration_seconds is None
        
        run.started_at = time.time() - 5
        assert run.duration_seconds is not None
        assert run.duration_seconds >= 5
        
        run.ended_at = run.started_at + 10
        assert abs(run.duration_seconds - 10) < 0.1
    
    def test_wait_time_calculation(self):
        """Test wait time calculation."""
        run = QueuedRun()
        run.created_at = time.time() - 3
        assert run.wait_seconds >= 3
        
        run.started_at = run.created_at + 2
        assert abs(run.wait_seconds - 2) < 0.1
    
    def test_can_retry(self):
        """Test retry eligibility."""
        run = QueuedRun(state=RunState.FAILED, retry_count=0, max_retries=3)
        assert run.can_retry()
        
        run.retry_count = 3
        assert not run.can_retry()
        
        run.retry_count = 0
        run.state = RunState.SUCCEEDED
        assert not run.can_retry()
    
    def test_to_dict(self):
        """Test serialization to dict."""
        run = QueuedRun(
            run_id="test123",
            agent_name="TestAgent",
            input_content="Hello",
        )
        d = run.to_dict()
        
        assert d["run_id"] == "test123"
        assert d["agent_name"] == "TestAgent"
        assert d["input_content"] == "Hello"
        assert d["state"] == "queued"
        assert d["priority"] == 1
    
    def test_from_dict(self):
        """Test deserialization from dict."""
        d = {
            "run_id": "test123",
            "agent_name": "TestAgent",
            "input_content": "Hello",
            "state": "running",
            "priority": 2,
        }
        run = QueuedRun.from_dict(d)
        
        assert run.run_id == "test123"
        assert run.agent_name == "TestAgent"
        assert run.state == RunState.RUNNING
        assert run.priority == RunPriority.HIGH
    
    def test_post_init_conversion(self):
        """Test automatic type conversion in __post_init__."""
        run = QueuedRun(state="running", priority=2)
        assert run.state == RunState.RUNNING
        assert run.priority == RunPriority.HIGH


class TestQueueConfig:
    """Tests for QueueConfig dataclass."""
    
    def test_default_values(self):
        """Test default values."""
        config = QueueConfig()
        assert config.max_concurrent_global == 4
        assert config.max_concurrent_per_agent == 2
        assert config.max_queue_size == 100
        assert config.enable_persistence
        assert config.db_path == ".praison/queue.db"
    
    def test_custom_values(self):
        """Test custom values."""
        config = QueueConfig(
            max_concurrent_global=8,
            max_queue_size=200,
            enable_persistence=False,
        )
        assert config.max_concurrent_global == 8
        assert config.max_queue_size == 200
        assert not config.enable_persistence
    
    def test_to_dict(self):
        """Test serialization."""
        config = QueueConfig()
        d = config.to_dict()
        assert "max_concurrent_global" in d
        assert "db_path" in d
    
    def test_from_dict(self):
        """Test deserialization."""
        d = {"max_concurrent_global": 10, "max_queue_size": 50}
        config = QueueConfig.from_dict(d)
        assert config.max_concurrent_global == 10
        assert config.max_queue_size == 50


class TestQueueStats:
    """Tests for QueueStats dataclass."""
    
    def test_active_count(self):
        """Test active count calculation."""
        stats = QueueStats(queued_count=5, running_count=3)
        assert stats.active_count == 8


class TestStreamChunk:
    """Tests for StreamChunk dataclass."""
    
    def test_creation(self):
        """Test chunk creation."""
        chunk = StreamChunk(
            run_id="test123",
            content="Hello",
            chunk_index=0,
        )
        assert chunk.run_id == "test123"
        assert chunk.content == "Hello"
        assert chunk.chunk_index == 0
        assert not chunk.is_final


class TestQueueEvent:
    """Tests for QueueEvent dataclass."""
    
    def test_creation(self):
        """Test event creation."""
        event = QueueEvent(
            event_type="run_started",
            run_id="test123",
        )
        assert event.event_type == "run_started"
        assert event.run_id == "test123"
        assert event.timestamp > 0
