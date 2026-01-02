"""
Queue Scheduler for PraisonAI.

Priority-based FIFO scheduler with concurrency limits.
"""

import asyncio
import logging
import time
import uuid
from collections import defaultdict
from typing import Any, Callable, Dict, List, Optional, Set

from .models import QueuedRun, RunState, RunPriority, QueueConfig, QueueEvent

logger = logging.getLogger(__name__)


class QueueFullError(Exception):
    """Raised when queue is at capacity."""
    pass


class RunNotFoundError(Exception):
    """Raised when a run is not found."""
    pass


class QueueScheduler:
    """
    Priority-based FIFO scheduler with concurrency limits.
    
    Runs are organized by priority (URGENT > HIGH > NORMAL > LOW),
    with FIFO ordering within each priority level.
    """
    
    def __init__(self, config: Optional[QueueConfig] = None):
        """
        Initialize scheduler.
        
        Args:
            config: Queue configuration. Uses defaults if not provided.
        """
        self.config = config or QueueConfig()
        
        # Priority queues: priority -> list of runs (FIFO order)
        self._queues: Dict[RunPriority, List[QueuedRun]] = {
            p: [] for p in RunPriority
        }
        
        # Running runs: run_id -> run
        self._running: Dict[str, QueuedRun] = {}
        
        # All runs by ID for quick lookup
        self._all_runs: Dict[str, QueuedRun] = {}
        
        # Lock for thread safety
        self._lock = asyncio.Lock()
        
        # Event callbacks
        self._event_callbacks: List[Callable[[QueueEvent], None]] = []
        
        # Cancellation tokens
        self._cancel_tokens: Set[str] = set()
    
    def add_event_callback(self, callback: Callable[[QueueEvent], None]) -> None:
        """Add a callback for queue events."""
        self._event_callbacks.append(callback)
    
    def remove_event_callback(self, callback: Callable[[QueueEvent], None]) -> None:
        """Remove an event callback."""
        if callback in self._event_callbacks:
            self._event_callbacks.remove(callback)
    
    def _emit_event(self, event: QueueEvent) -> None:
        """Emit an event to all callbacks."""
        for callback in self._event_callbacks:
            try:
                callback(event)
            except Exception as e:
                logger.error(f"Error in event callback: {e}")
    
    async def submit(
        self,
        run: QueuedRun,
        check_duplicate: bool = True,
    ) -> str:
        """
        Submit a run to the queue.
        
        Args:
            run: The run to submit.
            check_duplicate: If True, reject duplicate run_ids.
            
        Returns:
            The run_id.
            
        Raises:
            QueueFullError: If queue is at capacity.
            ValueError: If run_id already exists (when check_duplicate=True).
        """
        async with self._lock:
            # Check for duplicates
            if check_duplicate and run.run_id in self._all_runs:
                raise ValueError(f"Run {run.run_id} already exists")
            
            # Check queue capacity
            total_queued = sum(len(q) for q in self._queues.values())
            if total_queued >= self.config.max_queue_size:
                raise QueueFullError(
                    f"Queue is full ({total_queued}/{self.config.max_queue_size})"
                )
            
            # Ensure state is QUEUED
            run.state = RunState.QUEUED
            
            # Add to appropriate priority queue
            self._queues[run.priority].append(run)
            self._all_runs[run.run_id] = run
            
            logger.debug(f"Submitted run {run.run_id} with priority {run.priority.name}")
            
            self._emit_event(QueueEvent(
                event_type="run_submitted",
                run_id=run.run_id,
                data={"priority": run.priority.name, "agent": run.agent_name}
            ))
            
            return run.run_id
    
    async def next(self) -> Optional[QueuedRun]:
        """
        Get the next run to execute, respecting priority and concurrency limits.
        
        Returns:
            The next run, or None if no run is available.
        """
        async with self._lock:
            if not self._can_start_new():
                return None
            
            # Check priorities in order (URGENT first = highest value)
            for priority in reversed(list(RunPriority)):
                queue = self._queues[priority]
                
                for i, run in enumerate(queue):
                    if self._can_run(run):
                        # Remove from queue
                        queue.pop(i)
                        
                        # Update state
                        run.state = RunState.RUNNING
                        run.started_at = time.time()
                        
                        # Add to running
                        self._running[run.run_id] = run
                        
                        logger.debug(f"Starting run {run.run_id}")
                        
                        self._emit_event(QueueEvent(
                            event_type="run_started",
                            run_id=run.run_id,
                            data={"agent": run.agent_name}
                        ))
                        
                        return run
            
            return None
    
    async def complete(
        self,
        run_id: str,
        output: Optional[str] = None,
        metrics: Optional[Dict[str, Any]] = None,
    ) -> Optional[QueuedRun]:
        """
        Mark a run as completed successfully.
        
        Args:
            run_id: The run ID.
            output: The output content.
            metrics: Optional metrics.
            
        Returns:
            The completed run, or None if not found.
        """
        async with self._lock:
            run = self._running.pop(run_id, None)
            if run is None:
                logger.warning(f"Run {run_id} not found in running")
                return None
            
            run.state = RunState.SUCCEEDED
            run.ended_at = time.time()
            run.output_content = output
            if metrics:
                run.metrics.update(metrics)
            
            logger.debug(f"Completed run {run_id}")
            
            self._emit_event(QueueEvent(
                event_type="run_completed",
                run_id=run_id,
                data={"duration": run.duration_seconds}
            ))
            
            return run
    
    async def fail(
        self,
        run_id: str,
        error: str,
        metrics: Optional[Dict[str, Any]] = None,
    ) -> Optional[QueuedRun]:
        """
        Mark a run as failed.
        
        Args:
            run_id: The run ID.
            error: The error message.
            metrics: Optional metrics.
            
        Returns:
            The failed run, or None if not found.
        """
        async with self._lock:
            run = self._running.pop(run_id, None)
            if run is None:
                logger.warning(f"Run {run_id} not found in running")
                return None
            
            run.state = RunState.FAILED
            run.ended_at = time.time()
            run.error = error
            if metrics:
                run.metrics.update(metrics)
            
            logger.debug(f"Failed run {run_id}: {error}")
            
            self._emit_event(QueueEvent(
                event_type="run_failed",
                run_id=run_id,
                data={"error": error}
            ))
            
            return run
    
    async def cancel(self, run_id: str) -> bool:
        """
        Cancel a queued or running run.
        
        Args:
            run_id: The run ID to cancel.
            
        Returns:
            True if cancelled, False if not found.
        """
        async with self._lock:
            # Check if running
            if run_id in self._running:
                run = self._running.pop(run_id)
                run.state = RunState.CANCELLED
                run.ended_at = time.time()
                self._cancel_tokens.add(run_id)
                
                logger.debug(f"Cancelled running run {run_id}")
                
                self._emit_event(QueueEvent(
                    event_type="run_cancelled",
                    run_id=run_id,
                    data={"was_running": True}
                ))
                
                return True
            
            # Check if queued
            for priority in RunPriority:
                queue = self._queues[priority]
                for i, run in enumerate(queue):
                    if run.run_id == run_id:
                        queue.pop(i)
                        run.state = RunState.CANCELLED
                        run.ended_at = time.time()
                        
                        logger.debug(f"Cancelled queued run {run_id}")
                        
                        self._emit_event(QueueEvent(
                            event_type="run_cancelled",
                            run_id=run_id,
                            data={"was_running": False}
                        ))
                        
                        return True
            
            return False
    
    def is_cancelled(self, run_id: str) -> bool:
        """Check if a run has been cancelled."""
        return run_id in self._cancel_tokens
    
    def clear_cancel_token(self, run_id: str) -> None:
        """Clear a cancellation token."""
        self._cancel_tokens.discard(run_id)
    
    async def update_input(self, run_id: str, new_input: str) -> bool:
        """
        Update the input content of a queued run.
        
        Only works for runs in QUEUED state.
        
        Args:
            run_id: The run ID to update.
            new_input: The new input content.
            
        Returns:
            True if updated, False if not found or not editable.
        """
        async with self._lock:
            run = self._all_runs.get(run_id)
            if run is None:
                return False
            
            if run.state != RunState.QUEUED:
                logger.warning(f"Cannot edit run {run_id} in state {run.state}")
                return False
            
            run.input_content = new_input
            
            logger.debug(f"Updated input for run {run_id}")
            
            self._emit_event(QueueEvent(
                event_type="run_updated",
                run_id=run_id,
                data={"new_input": new_input[:50]}
            ))
            
            return True
    
    async def retry(self, run_id: str) -> Optional[str]:
        """
        Retry a failed run.
        
        Creates a new run with incremented retry count and link to parent.
        
        Args:
            run_id: The run ID to retry.
            
        Returns:
            The new run_id, or None if retry not allowed.
        """
        async with self._lock:
            # Find the original run
            original = self._all_runs.get(run_id)
            if original is None:
                logger.warning(f"Run {run_id} not found for retry")
                return None
            
            if not original.can_retry():
                logger.warning(
                    f"Run {run_id} cannot be retried "
                    f"(state={original.state}, retries={original.retry_count}/{original.max_retries})"
                )
                return None
            
            # Create new run
            new_run = QueuedRun(
                run_id=str(uuid.uuid4())[:8],
                agent_name=original.agent_name,
                input_content=original.input_content,
                state=RunState.QUEUED,
                priority=original.priority,
                session_id=original.session_id,
                trace_id=original.trace_id,
                workspace=original.workspace,
                user_id=original.user_id,
                retry_count=original.retry_count + 1,
                max_retries=original.max_retries,
                parent_run_id=original.run_id,
                config=original.config.copy(),
            )
        
        # Submit outside lock to avoid deadlock
        await self.submit(new_run, check_duplicate=True)
        
        logger.debug(f"Retrying run {run_id} as {new_run.run_id}")
        
        self._emit_event(QueueEvent(
            event_type="run_retried",
            run_id=new_run.run_id,
            data={"parent_run_id": run_id, "retry_count": new_run.retry_count}
        ))
        
        return new_run.run_id
    
    async def pause(self, run_id: str) -> bool:
        """
        Pause a running run.
        
        Note: The worker must check for pause state and handle accordingly.
        """
        async with self._lock:
            if run_id not in self._running:
                return False
            
            run = self._running[run_id]
            run.state = RunState.PAUSED
            
            self._emit_event(QueueEvent(
                event_type="run_paused",
                run_id=run_id,
            ))
            
            return True
    
    async def resume(self, run_id: str) -> bool:
        """Resume a paused run."""
        async with self._lock:
            if run_id not in self._running:
                return False
            
            run = self._running[run_id]
            if run.state != RunState.PAUSED:
                return False
            
            run.state = RunState.RUNNING
            
            self._emit_event(QueueEvent(
                event_type="run_resumed",
                run_id=run_id,
            ))
            
            return True
    
    def get_run(self, run_id: str) -> Optional[QueuedRun]:
        """Get a run by ID."""
        return self._all_runs.get(run_id)
    
    def get_queued(self) -> List[QueuedRun]:
        """Get all queued runs in priority order."""
        result = []
        for priority in reversed(list(RunPriority)):
            result.extend(self._queues[priority])
        return result
    
    def get_running(self) -> List[QueuedRun]:
        """Get all running runs."""
        return list(self._running.values())
    
    def get_all(self) -> List[QueuedRun]:
        """Get all runs."""
        return list(self._all_runs.values())
    
    @property
    def queued_count(self) -> int:
        """Number of queued runs."""
        return sum(len(q) for q in self._queues.values())
    
    @property
    def running_count(self) -> int:
        """Number of running runs."""
        return len(self._running)
    
    def _can_start_new(self) -> bool:
        """Check if we can start a new run (global limit)."""
        return len(self._running) < self.config.max_concurrent_global
    
    def _can_run(self, run: QueuedRun) -> bool:
        """Check if a specific run can start (per-agent and per-workspace limits)."""
        # Count running by agent
        agent_count = sum(
            1 for r in self._running.values()
            if r.agent_name == run.agent_name
        )
        if agent_count >= self.config.max_concurrent_per_agent:
            return False
        
        # Count running by workspace
        if run.workspace:
            workspace_count = sum(
                1 for r in self._running.values()
                if r.workspace == run.workspace
            )
            if workspace_count >= self.config.max_concurrent_per_workspace:
                return False
        
        return True
    
    async def clear_queue(self) -> int:
        """Clear all queued (not running) runs."""
        async with self._lock:
            count = 0
            for priority in RunPriority:
                count += len(self._queues[priority])
                for run in self._queues[priority]:
                    run.state = RunState.CANCELLED
                    del self._all_runs[run.run_id]
                self._queues[priority] = []
            
            return count
    
    def load_runs(self, runs: List[QueuedRun]) -> None:
        """
        Load runs (e.g., from persistence after restart).
        
        Queued runs are added to queues, running runs are re-queued.
        """
        for run in runs:
            if run.state == RunState.RUNNING:
                # Re-queue running runs (they were interrupted)
                run.state = RunState.QUEUED
                run.started_at = None
            
            if run.state == RunState.QUEUED:
                self._queues[run.priority].append(run)
            
            self._all_runs[run.run_id] = run
        
        logger.info(f"Loaded {len(runs)} runs from persistence")
