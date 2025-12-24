"""
Unit tests for the Background module.

Tests cover:
- BackgroundTask creation and status management
- BackgroundRunner task submission
- Task cancellation and timeout
- Concurrent execution
"""

import pytest
import asyncio
from datetime import datetime

from praisonaiagents.background.task import BackgroundTask, TaskStatus
from praisonaiagents.background.config import BackgroundConfig
from praisonaiagents.background.runner import BackgroundRunner


# =============================================================================
# BackgroundTask Tests
# =============================================================================

class TestBackgroundTask:
    """Tests for BackgroundTask class."""
    
    def test_task_creation(self):
        """Test creating a task."""
        task = BackgroundTask(name="test_task")
        assert task.name == "test_task"
        assert task.status == TaskStatus.PENDING
        assert task.progress == 0.0
        assert not task.is_running
        assert not task.is_completed
    
    def test_task_start(self):
        """Test starting a task."""
        task = BackgroundTask(name="test")
        task.start()
        
        assert task.status == TaskStatus.RUNNING
        assert task.is_running
        assert task.started_at is not None
    
    def test_task_complete(self):
        """Test completing a task."""
        task = BackgroundTask(name="test")
        task.start()
        task.complete(result="success")
        
        assert task.status == TaskStatus.COMPLETED
        assert task.is_completed
        assert task.is_successful
        assert task.result == "success"
        assert task.progress == 1.0
        assert task.completed_at is not None
    
    def test_task_fail(self):
        """Test failing a task."""
        task = BackgroundTask(name="test")
        task.start()
        task.fail("Something went wrong")
        
        assert task.status == TaskStatus.FAILED
        assert task.is_completed
        assert not task.is_successful
        assert task.error == "Something went wrong"
    
    def test_task_cancel(self):
        """Test cancelling a task."""
        task = BackgroundTask(name="test")
        task.start()
        task.cancel()
        
        assert task.status == TaskStatus.CANCELLED
        assert task.is_completed
        assert task.should_cancel()
    
    def test_task_progress(self):
        """Test updating task progress."""
        task = BackgroundTask(name="test")
        task.start()
        
        task.update_progress(0.5, "Halfway done")
        
        assert task.progress == 0.5
        assert task.metadata.get("last_message") == "Halfway done"
    
    def test_task_progress_bounds(self):
        """Test that progress is bounded."""
        task = BackgroundTask(name="test")
        
        task.update_progress(-0.5)
        assert task.progress == 0.0
        
        task.update_progress(1.5)
        assert task.progress == 1.0
    
    def test_task_duration(self):
        """Test task duration calculation."""
        task = BackgroundTask(name="test")
        
        assert task.duration_seconds is None
        
        task.start()
        assert task.duration_seconds is not None
        assert task.duration_seconds >= 0
    
    def test_task_to_dict(self):
        """Test task serialization."""
        task = BackgroundTask(name="test")
        task.start()
        task.complete("result")
        
        data = task.to_dict()
        
        assert data["name"] == "test"
        assert data["status"] == "completed"
        assert data["result"] == "result"
        assert "created_at" in data
        assert "started_at" in data
        assert "completed_at" in data


# =============================================================================
# BackgroundConfig Tests
# =============================================================================

class TestBackgroundConfig:
    """Tests for BackgroundConfig class."""
    
    def test_config_defaults(self):
        """Test default configuration."""
        config = BackgroundConfig()
        
        assert config.max_concurrent_tasks == 5
        assert config.default_timeout is None
        assert config.auto_cleanup
        assert config.cleanup_delay == 300.0
    
    def test_config_custom(self):
        """Test custom configuration."""
        config = BackgroundConfig(
            max_concurrent_tasks=10,
            default_timeout=60.0,
            auto_cleanup=False
        )
        
        assert config.max_concurrent_tasks == 10
        assert config.default_timeout == 60.0
        assert not config.auto_cleanup


# =============================================================================
# BackgroundRunner Tests
# =============================================================================

class TestBackgroundRunner:
    """Tests for BackgroundRunner class."""
    
    @pytest.fixture
    def runner(self):
        """Create a test runner."""
        return BackgroundRunner()
    
    @pytest.mark.asyncio
    async def test_submit_sync_function(self, runner):
        """Test submitting a sync function."""
        def sync_func(x):
            return x * 2
        
        task = await runner.submit(func=sync_func, args=(5,), name="double")
        result = await task.wait(timeout=5.0)
        
        assert result == 10
        assert task.is_successful
    
    @pytest.mark.asyncio
    async def test_submit_async_function(self, runner):
        """Test submitting an async function."""
        async def async_func(x):
            await asyncio.sleep(0.1)
            return x * 3
        
        task = await runner.submit(func=async_func, args=(5,), name="triple")
        result = await task.wait(timeout=5.0)
        
        assert result == 15
        assert task.is_successful
    
    @pytest.mark.asyncio
    async def test_submit_with_kwargs(self, runner):
        """Test submitting with keyword arguments."""
        def func_with_kwargs(a, b=10):
            return a + b
        
        task = await runner.submit(
            func=func_with_kwargs,
            args=(5,),
            kwargs={"b": 20}
        )
        result = await task.wait(timeout=5.0)
        
        assert result == 25
    
    @pytest.mark.asyncio
    async def test_task_timeout(self, runner):
        """Test task timeout."""
        async def slow_func():
            await asyncio.sleep(10)
            return "done"
        
        task = await runner.submit(func=slow_func, timeout=0.1)
        
        await asyncio.sleep(0.3)
        
        assert task.status == TaskStatus.FAILED
        assert "timed out" in task.error
    
    @pytest.mark.asyncio
    async def test_task_failure(self, runner):
        """Test task that raises exception."""
        def failing_func():
            raise ValueError("Test error")
        
        task = await runner.submit(func=failing_func)
        
        await asyncio.sleep(0.1)
        
        assert task.status == TaskStatus.FAILED
        assert "Test error" in task.error
    
    @pytest.mark.asyncio
    async def test_cancel_task(self, runner):
        """Test cancelling a task."""
        async def long_running():
            await asyncio.sleep(10)
            return "done"
        
        task = await runner.submit(func=long_running)
        
        await asyncio.sleep(0.1)
        result = await runner.cancel_task(task.id)
        
        assert result
        assert task.status == TaskStatus.CANCELLED
    
    @pytest.mark.asyncio
    async def test_get_task(self, runner):
        """Test getting a task by ID."""
        task = await runner.submit(func=lambda: "test")
        
        retrieved = runner.get_task(task.id)
        
        assert retrieved is not None
        assert retrieved.id == task.id
    
    @pytest.mark.asyncio
    async def test_list_tasks(self, runner):
        """Test listing tasks."""
        await runner.submit(func=lambda: "a", name="task_a")
        await runner.submit(func=lambda: "b", name="task_b")
        
        await asyncio.sleep(0.2)
        
        tasks = runner.list_tasks()
        
        assert len(tasks) == 2
    
    @pytest.mark.asyncio
    async def test_list_tasks_by_status(self, runner):
        """Test listing tasks filtered by status."""
        await runner.submit(func=lambda: "a")
        await runner.submit(func=lambda: "b")
        
        await asyncio.sleep(0.2)
        
        completed = runner.list_tasks(status=TaskStatus.COMPLETED)
        
        assert len(completed) == 2
    
    @pytest.mark.asyncio
    async def test_clear_completed(self, runner):
        """Test clearing completed tasks."""
        await runner.submit(func=lambda: "a")
        await runner.submit(func=lambda: "b")
        
        await asyncio.sleep(0.2)
        
        assert len(runner.tasks) == 2
        
        runner.clear_completed()
        
        assert len(runner.tasks) == 0
    
    @pytest.mark.asyncio
    async def test_on_complete_callback(self, runner):
        """Test on_complete callback."""
        callback_called = []
        
        def on_complete(task):
            callback_called.append(task.id)
        
        task = await runner.submit(
            func=lambda: "result",
            on_complete=on_complete
        )
        
        await task.wait(timeout=5.0)
        
        assert task.id in callback_called
    
    @pytest.mark.asyncio
    async def test_concurrent_execution(self, runner):
        """Test concurrent task execution."""
        results = []
        
        async def task_func(n):
            await asyncio.sleep(0.1)
            results.append(n)
            return n
        
        tasks = []
        for i in range(3):
            task = await runner.submit(func=task_func, args=(i,))
            tasks.append(task)
        
        await runner.wait_all(timeout=5.0)
        
        assert len(results) == 3
        assert all(t.is_successful for t in tasks)
    
    @pytest.mark.asyncio
    async def test_max_concurrent_limit(self):
        """Test max concurrent tasks limit."""
        config = BackgroundConfig(max_concurrent_tasks=2)
        runner = BackgroundRunner(config=config)
        
        execution_times = []
        
        async def tracked_func(n):
            execution_times.append((n, "start", asyncio.get_event_loop().time()))
            await asyncio.sleep(0.2)
            execution_times.append((n, "end", asyncio.get_event_loop().time()))
            return n
        
        tasks = []
        for i in range(4):
            task = await runner.submit(func=tracked_func, args=(i,))
            tasks.append(task)
        
        await runner.wait_all(timeout=5.0)
        
        # All tasks should complete
        assert all(t.is_successful for t in tasks)
    
    @pytest.mark.asyncio
    async def test_wait_all(self, runner):
        """Test waiting for all tasks."""
        async def slow_func(n):
            await asyncio.sleep(0.1 * n)
            return n
        
        for i in range(1, 4):
            await runner.submit(func=slow_func, args=(i,))
        
        tasks = await runner.wait_all(timeout=5.0)
        
        assert len(tasks) == 3
        assert all(t.is_completed for t in tasks)
    
    @pytest.mark.asyncio
    async def test_cancel_all(self, runner):
        """Test cancelling all tasks."""
        async def long_func():
            await asyncio.sleep(10)
        
        for _ in range(3):
            await runner.submit(func=long_func)
        
        await asyncio.sleep(0.1)
        await runner.cancel_all()
        
        assert all(t.status == TaskStatus.CANCELLED for t in runner.tasks)
    
    @pytest.mark.asyncio
    async def test_stop_runner(self, runner):
        """Test stopping the runner."""
        async def long_func():
            await asyncio.sleep(10)
        
        await runner.submit(func=long_func)
        await asyncio.sleep(0.1)
        
        await runner.stop()
        
        assert all(t.status == TaskStatus.CANCELLED for t in runner.tasks)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
