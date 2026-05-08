"""
Unit tests for AsyncAgentScheduler exception handling and cleanup.

Tests for:
- stop() always sets is_running=False via finally block
- stop() timeout path: cancels task and handles CancelledError cleanly
- stop() timeout path: logs non-CancelledError exceptions from cancelled task
- _run_schedule() always sets is_running=False via finally block on exception
- Basic start/stop lifecycle
"""

import asyncio
import pytest
import warnings
from unittest.mock import AsyncMock, Mock, patch

with warnings.catch_warnings():
    warnings.simplefilter("ignore", PendingDeprecationWarning)
    from praisonai.async_agent_scheduler import AsyncAgentScheduler, create_async_agent_scheduler


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_scheduler(task="Test task"):
    """Return a scheduler wired to a mock agent that does nothing."""
    mock_agent = Mock()
    mock_agent.astart = AsyncMock(return_value="result")
    return AsyncAgentScheduler(mock_agent, task)


# ---------------------------------------------------------------------------
# Initialization
# ---------------------------------------------------------------------------

class TestAsyncAgentSchedulerInit:
    """Test AsyncAgentScheduler initialization."""

    def test_init_default_values(self):
        scheduler = _make_scheduler()
        assert scheduler.is_running is False
        assert scheduler._task is None
        assert scheduler._execution_count == 0
        assert scheduler._success_count == 0
        assert scheduler._failure_count == 0

    def test_init_with_callbacks(self):
        mock_agent = Mock()
        on_success = Mock()
        on_failure = Mock()
        scheduler = AsyncAgentScheduler(
            mock_agent, "task", on_success=on_success, on_failure=on_failure
        )
        assert scheduler.on_success is on_success
        assert scheduler.on_failure is on_failure

    def test_factory_function(self):
        mock_agent = Mock()
        scheduler = create_async_agent_scheduler(mock_agent, "task")
        assert isinstance(scheduler, AsyncAgentScheduler)
        assert scheduler.task == "task"


# ---------------------------------------------------------------------------
# stop() – finally always clears is_running
# ---------------------------------------------------------------------------

class TestStopAlwaysClearsIsRunning:
    """stop() must set is_running=False regardless of how the task ends."""

    @pytest.mark.asyncio
    async def test_stop_sets_is_running_false_on_normal_exit(self):
        scheduler = _make_scheduler()
        await scheduler.start("hourly", run_immediately=False)
        assert scheduler.is_running is True

        await scheduler.stop()
        assert scheduler.is_running is False

    @pytest.mark.asyncio
    async def test_stop_returns_true_when_not_running(self):
        scheduler = _make_scheduler()
        result = await scheduler.stop()
        assert result is True
        assert scheduler.is_running is False

    @pytest.mark.asyncio
    async def test_stop_logs_task_exception_and_returns_true(self):
        """Task exceptions from wait_for should be logged and stop should return True."""
        scheduler = _make_scheduler()
        scheduler.is_running = True
        # Async primitives are now lazily created in start(); tests that bypass
        # start() must initialize them explicitly.
        scheduler._ensure_async_primitives()

        # Create a task that raises a non-cancellation exception
        async def _raise():
            raise RuntimeError("unexpected")

        scheduler._task = asyncio.create_task(_raise())
        scheduler._stop_event.set()

        # The exception should be caught, logged, and stop should return True
        with patch("praisonai.async_agent_scheduler.logger") as mock_logger:
            result = await scheduler.stop()

        assert result is True
        assert scheduler.is_running is False
        mock_logger.error.assert_called()
        logged_msg = mock_logger.error.call_args[0][0]
        assert "unexpected" in logged_msg


# ---------------------------------------------------------------------------
# stop() – timeout / cancel path
# ---------------------------------------------------------------------------

class TestStopTimeoutCancelPath:
    """Verify the timeout → cancel branch of stop()."""

    @pytest.mark.asyncio
    async def test_stop_cancels_task_on_timeout(self):
        """When wait_for times out, task.cancel() must be called."""
        scheduler = _make_scheduler()
        scheduler.is_running = True
        scheduler._ensure_async_primitives()

        # A task that sleeps forever so wait_for always times out
        async def _sleep_forever():
            try:
                await asyncio.sleep(3600)
            except asyncio.CancelledError:
                raise

        scheduler._task = asyncio.create_task(_sleep_forever())
        scheduler._stop_event.set()

        with patch("asyncio.wait_for", side_effect=asyncio.TimeoutError):
            await scheduler.stop()

        assert scheduler.is_running is False

    @pytest.mark.asyncio
    async def test_stop_handles_cancelled_error_silently(self):
        """CancelledError after cancel() must not propagate out of stop()."""
        scheduler = _make_scheduler()
        scheduler.is_running = True
        scheduler._ensure_async_primitives()

        async def _cancellable():
            await asyncio.sleep(3600)

        scheduler._task = asyncio.create_task(_cancellable())
        scheduler._stop_event.set()

        # Simulate: wait_for times out, then task.cancel() raises CancelledError
        with patch("asyncio.wait_for", side_effect=asyncio.TimeoutError):
            # Should not raise
            result = await scheduler.stop()

        assert result is True
        assert scheduler.is_running is False

    @pytest.mark.asyncio
    async def test_stop_logs_non_cancelled_exception_from_cancelled_task(self):
        """Non-CancelledError from a cancelled task must be logged, not raised."""
        scheduler = _make_scheduler()
        scheduler.is_running = True
        scheduler._ensure_async_primitives()

        # Simulate a task that raises a plain Exception when awaited after cancel
        future = asyncio.get_event_loop().create_future()
        future.set_exception(RuntimeError("task blew up"))
        scheduler._task = future
        scheduler._stop_event.set()

        with patch("asyncio.wait_for", side_effect=asyncio.TimeoutError), \
             patch("praisonai.async_agent_scheduler.logger") as mock_logger:
            await scheduler.stop()

        # The error should have been logged
        mock_logger.error.assert_called()
        logged_msg = mock_logger.error.call_args[0][0]
        assert "task blew up" in logged_msg
        assert scheduler.is_running is False


# ---------------------------------------------------------------------------
# _run_schedule() – finally always clears is_running
# ---------------------------------------------------------------------------

class TestRunScheduleFinally:
    """_run_schedule() must set is_running=False in all exit paths."""

    @pytest.mark.asyncio
    async def test_run_schedule_clears_is_running_on_stop_event(self):
        scheduler = _make_scheduler()
        scheduler.is_running = True
        scheduler._ensure_async_primitives()

        # Set the stop event immediately so the loop exits on first check
        scheduler._stop_event.set()

        await scheduler._run_schedule(interval=3600, max_retries=1)
        assert scheduler.is_running is False

    @pytest.mark.asyncio
    async def test_run_schedule_clears_is_running_on_exception(self):
        """If _execute_with_retry raises unexpectedly, is_running must clear."""
        scheduler = _make_scheduler()
        scheduler.is_running = True

        async def _boom(max_retries):
            raise RuntimeError("unexpected internal error")

        scheduler._execute_with_retry = _boom

        with pytest.raises(RuntimeError):
            await scheduler._run_schedule(interval=3600, max_retries=1)

        assert scheduler.is_running is False

    @pytest.mark.asyncio
    async def test_run_schedule_clears_is_running_on_cancellation(self):
        """CancelledError propagates but is_running is still cleared."""
        scheduler = _make_scheduler()
        scheduler.is_running = True

        async def _run():
            await scheduler._run_schedule(interval=3600, max_retries=1)

        task = asyncio.create_task(_run())
        await asyncio.sleep(0)  # Allow task to start
        task.cancel()

        with pytest.raises(asyncio.CancelledError):
            await task

        assert scheduler.is_running is False


# ---------------------------------------------------------------------------
# Full lifecycle
# ---------------------------------------------------------------------------

class TestAsyncAgentSchedulerLifecycle:
    """End-to-end start/stop lifecycle tests."""

    @pytest.mark.asyncio
    async def test_start_sets_is_running(self):
        scheduler = _make_scheduler()
        result = await scheduler.start("*/1s", run_immediately=False)
        assert result is True
        assert scheduler.is_running is True
        await scheduler.stop()

    @pytest.mark.asyncio
    async def test_start_already_running_returns_false(self):
        scheduler = _make_scheduler()
        await scheduler.start("hourly", run_immediately=False)
        result = await scheduler.start("hourly", run_immediately=False)
        assert result is False
        await scheduler.stop()

    @pytest.mark.asyncio
    async def test_start_invalid_schedule_returns_false(self):
        scheduler = _make_scheduler()
        result = await scheduler.start("bad_format")
        assert result is False
        assert scheduler.is_running is False

    @pytest.mark.asyncio
    async def test_get_stats_initial_state(self):
        scheduler = _make_scheduler()
        stats = await scheduler.get_stats()
        assert stats["is_running"] is False
        assert stats["total_executions"] == 0
        assert stats["successful_executions"] == 0
        assert stats["failed_executions"] == 0
        assert stats["success_rate"] == 0

    @pytest.mark.asyncio
    async def test_execute_once_success(self):
        scheduler = _make_scheduler()
        result = await scheduler.execute_once()
        assert result == "result"

    @pytest.mark.asyncio
    async def test_execute_once_failure_propagates(self):
        mock_agent = Mock()
        mock_agent.astart = AsyncMock(side_effect=RuntimeError("boom"))
        scheduler = AsyncAgentScheduler(mock_agent, "task")
        with pytest.raises(RuntimeError, match="boom"):
            await scheduler.execute_once()
