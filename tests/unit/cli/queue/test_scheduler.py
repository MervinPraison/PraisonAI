"""Tests for Queue Scheduler."""

import pytest
import asyncio
from praisonai.cli.features.queue.models import QueuedRun, RunState, RunPriority, QueueConfig
from praisonai.cli.features.queue.scheduler import QueueScheduler, QueueFullError


class TestQueueScheduler:
    """Tests for QueueScheduler."""
    
    @pytest.fixture
    def config(self):
        """Create test config."""
        return QueueConfig(
            max_concurrent_global=2,
            max_concurrent_per_agent=1,
            max_queue_size=5,
        )
    
    @pytest.fixture
    def scheduler(self, config):
        """Create test scheduler."""
        return QueueScheduler(config)
    
    @pytest.mark.asyncio
    async def test_submit_run(self, scheduler):
        """Test submitting a run."""
        run = QueuedRun(
            agent_name="TestAgent",
            input_content="Hello",
        )
        
        run_id = await scheduler.submit(run)
        
        assert run_id == run.run_id
        assert scheduler.queued_count == 1
        assert run.state == RunState.QUEUED
    
    @pytest.mark.asyncio
    async def test_submit_duplicate_rejected(self, scheduler):
        """Test duplicate run_id is rejected."""
        run = QueuedRun(run_id="test123", agent_name="TestAgent")
        await scheduler.submit(run)
        
        run2 = QueuedRun(run_id="test123", agent_name="TestAgent")
        with pytest.raises(ValueError, match="already exists"):
            await scheduler.submit(run2)
    
    @pytest.mark.asyncio
    async def test_queue_full_error(self, scheduler):
        """Test queue full error."""
        for i in range(5):
            run = QueuedRun(agent_name="TestAgent", input_content=f"Test {i}")
            await scheduler.submit(run)
        
        run = QueuedRun(agent_name="TestAgent", input_content="Overflow")
        with pytest.raises(QueueFullError):
            await scheduler.submit(run)
    
    @pytest.mark.asyncio
    async def test_next_returns_highest_priority(self, scheduler):
        """Test next() returns highest priority run."""
        low = QueuedRun(agent_name="Agent1", priority=RunPriority.LOW)
        normal = QueuedRun(agent_name="Agent2", priority=RunPriority.NORMAL)
        high = QueuedRun(agent_name="Agent3", priority=RunPriority.HIGH)
        
        await scheduler.submit(low)
        await scheduler.submit(normal)
        await scheduler.submit(high)
        
        next_run = await scheduler.next()
        assert next_run.priority == RunPriority.HIGH
        assert next_run.state == RunState.RUNNING
    
    @pytest.mark.asyncio
    async def test_fifo_within_priority(self, scheduler):
        """Test FIFO ordering within same priority."""
        run1 = QueuedRun(run_id="first", agent_name="Agent1")
        run2 = QueuedRun(run_id="second", agent_name="Agent2")
        
        await scheduler.submit(run1)
        await scheduler.submit(run2)
        
        next_run = await scheduler.next()
        assert next_run.run_id == "first"
    
    @pytest.mark.asyncio
    async def test_concurrency_limit_global(self, scheduler):
        """Test global concurrency limit."""
        run1 = QueuedRun(agent_name="Agent1")
        run2 = QueuedRun(agent_name="Agent2")
        run3 = QueuedRun(agent_name="Agent3")
        
        await scheduler.submit(run1)
        await scheduler.submit(run2)
        await scheduler.submit(run3)
        
        # Start first two
        await scheduler.next()
        await scheduler.next()
        
        # Third should not start (limit is 2)
        next_run = await scheduler.next()
        assert next_run is None
        assert scheduler.running_count == 2
    
    @pytest.mark.asyncio
    async def test_concurrency_limit_per_agent(self, scheduler):
        """Test per-agent concurrency limit."""
        run1 = QueuedRun(agent_name="SameAgent")
        run2 = QueuedRun(agent_name="SameAgent")
        run3 = QueuedRun(agent_name="DifferentAgent")
        
        await scheduler.submit(run1)
        await scheduler.submit(run2)
        await scheduler.submit(run3)
        
        # Start first
        await scheduler.next()
        
        # Second same agent should not start
        next_run = await scheduler.next()
        assert next_run.agent_name == "DifferentAgent"
    
    @pytest.mark.asyncio
    async def test_complete_run(self, scheduler):
        """Test completing a run."""
        run = QueuedRun(agent_name="TestAgent")
        await scheduler.submit(run)
        await scheduler.next()
        
        completed = await scheduler.complete(run.run_id, output="Result")
        
        assert completed.state == RunState.SUCCEEDED
        assert completed.output_content == "Result"
        assert completed.ended_at is not None
        assert scheduler.running_count == 0
    
    @pytest.mark.asyncio
    async def test_fail_run(self, scheduler):
        """Test failing a run."""
        run = QueuedRun(agent_name="TestAgent")
        await scheduler.submit(run)
        await scheduler.next()
        
        failed = await scheduler.fail(run.run_id, error="Test error")
        
        assert failed.state == RunState.FAILED
        assert failed.error == "Test error"
        assert failed.ended_at is not None
    
    @pytest.mark.asyncio
    async def test_cancel_queued_run(self, scheduler):
        """Test cancelling a queued run."""
        run = QueuedRun(agent_name="TestAgent")
        await scheduler.submit(run)
        
        result = await scheduler.cancel(run.run_id)
        
        assert result is True
        assert scheduler.queued_count == 0
    
    @pytest.mark.asyncio
    async def test_cancel_running_run(self, scheduler):
        """Test cancelling a running run."""
        run = QueuedRun(agent_name="TestAgent")
        await scheduler.submit(run)
        await scheduler.next()
        
        result = await scheduler.cancel(run.run_id)
        
        assert result is True
        assert scheduler.running_count == 0
        assert scheduler.is_cancelled(run.run_id)
    
    @pytest.mark.asyncio
    async def test_retry_failed_run(self, scheduler):
        """Test retrying a failed run."""
        run = QueuedRun(agent_name="TestAgent", input_content="Hello")
        await scheduler.submit(run)
        await scheduler.next()
        await scheduler.fail(run.run_id, error="Test error")
        
        new_id = await scheduler.retry(run.run_id)
        
        assert new_id is not None
        assert new_id != run.run_id
        
        new_run = scheduler.get_run(new_id)
        assert new_run.retry_count == 1
        assert new_run.parent_run_id == run.run_id
        assert new_run.input_content == "Hello"
    
    @pytest.mark.asyncio
    async def test_retry_max_retries_exceeded(self, scheduler):
        """Test retry fails when max retries exceeded."""
        run = QueuedRun(
            agent_name="TestAgent",
            retry_count=3,
            max_retries=3,
            state=RunState.FAILED,
        )
        await scheduler.submit(run, check_duplicate=False)
        
        new_id = await scheduler.retry(run.run_id)
        assert new_id is None
    
    @pytest.mark.asyncio
    async def test_get_queued(self, scheduler):
        """Test getting queued runs."""
        run1 = QueuedRun(agent_name="Agent1", priority=RunPriority.LOW)
        run2 = QueuedRun(agent_name="Agent2", priority=RunPriority.HIGH)
        
        await scheduler.submit(run1)
        await scheduler.submit(run2)
        
        queued = scheduler.get_queued()
        
        assert len(queued) == 2
        # Should be in priority order
        assert queued[0].priority == RunPriority.HIGH
    
    @pytest.mark.asyncio
    async def test_clear_queue(self, scheduler):
        """Test clearing the queue."""
        for i in range(3):
            run = QueuedRun(agent_name=f"Agent{i}")
            await scheduler.submit(run)
        
        count = await scheduler.clear_queue()
        
        assert count == 3
        assert scheduler.queued_count == 0
    
    @pytest.mark.asyncio
    async def test_load_runs(self, scheduler):
        """Test loading runs from persistence."""
        runs = [
            QueuedRun(run_id="run1", agent_name="Agent1", state=RunState.QUEUED),
            QueuedRun(run_id="run2", agent_name="Agent2", state=RunState.RUNNING),
        ]
        
        scheduler.load_runs(runs)
        
        # Running run should be re-queued
        assert scheduler.queued_count == 2
        assert scheduler.running_count == 0
    
    @pytest.mark.asyncio
    async def test_event_callbacks(self, scheduler):
        """Test event callbacks are called."""
        events = []
        
        def callback(event):
            events.append(event)
        
        scheduler.add_event_callback(callback)
        
        run = QueuedRun(agent_name="TestAgent")
        await scheduler.submit(run)
        
        assert len(events) == 1
        assert events[0].event_type == "run_submitted"
