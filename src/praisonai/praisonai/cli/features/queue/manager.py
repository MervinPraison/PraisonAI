"""
Queue Manager for PraisonAI.

High-level interface that coordinates scheduler, workers, and persistence.
"""

import asyncio
import logging
import os
import time
from typing import Any, Callable, Coroutine, Dict, List, Optional

from .models import QueuedRun, RunState, RunPriority, QueueConfig, QueueStats, QueueEvent
from .scheduler import QueueScheduler, QueueFullError
from .worker import WorkerPool
from .persistence import QueuePersistence

logger = logging.getLogger(__name__)


class QueueManager:
    """
    High-level queue manager that coordinates all queue components.
    
    Provides a unified interface for:
    - Submitting and managing runs
    - Starting/stopping workers
    - Persistence and crash recovery
    - Event handling
    """
    
    # Runtime tools registry - stores tools that can't be serialized to JSON
    # Key: run_id or "default", Value: list of tool callables
    _tools_registry: Dict[str, list] = {}
    
    def __init__(
        self,
        config: Optional[QueueConfig] = None,
        on_output: Optional[Callable[[str, str], Coroutine[Any, Any, None]]] = None,
        on_complete: Optional[Callable[[str, QueuedRun], Coroutine[Any, Any, None]]] = None,
        on_error: Optional[Callable[[str, Exception], Coroutine[Any, Any, None]]] = None,
        on_event: Optional[Callable[[QueueEvent], Coroutine[Any, Any, None]]] = None,
        default_tools: Optional[list] = None,
    ):
        """
        Initialize queue manager.
        
        Args:
            config: Queue configuration.
            on_output: Callback for streaming output.
            on_complete: Callback when run completes.
            on_error: Callback when run fails.
            on_event: Callback for queue events.
            default_tools: Default tools to use for all runs (stored in runtime registry).
        """
        self.config = config or QueueConfig()
        
        # Initialize components
        self.scheduler = QueueScheduler(self.config)
        self.persistence = QueuePersistence(self.config.db_path) if self.config.enable_persistence else None
        
        # Store callbacks
        self._on_output = on_output
        self._on_complete = on_complete
        self._on_error = on_error
        self._on_event = on_event
        
        # Worker pool (created on start)
        self.workers: Optional[WorkerPool] = None
        
        # Autosave task
        self._autosave_task: Optional[asyncio.Task] = None
        
        # Running state
        self._running = False
        
        # Session tracking
        self._current_session_id: Optional[str] = None
        
        # Store default tools in registry
        if default_tools:
            QueueManager._tools_registry["default"] = default_tools
    
    async def start(self, recover: bool = True) -> None:
        """
        Start the queue manager.
        
        Args:
            recover: If True, recover pending runs from persistence.
        """
        if self._running:
            return
        
        logger.info("Starting queue manager")
        
        # Initialize persistence
        if self.persistence:
            self.persistence.initialize()
            
            if recover:
                await self._recover_runs()
        
        # Create and start worker pool
        self.workers = WorkerPool(
            scheduler=self.scheduler,
            on_output=self._on_output,
            on_complete=self._wrap_complete_callback(),
            on_error=self._wrap_error_callback(),
            on_event=self._on_event,
            max_workers=self.config.max_concurrent_global,
            poll_interval=self.config.worker_poll_interval,
            stream_buffer_size=self.config.stream_buffer_size,
        )
        
        await self.workers.start()
        
        # Start autosave
        if self.persistence and self.config.autosave_interval_seconds > 0:
            self._autosave_task = asyncio.create_task(
                self._autosave_loop(),
                name="queue-autosave"
            )
        
        self._running = True
        logger.info("Queue manager started")
    
    async def stop(self, timeout: float = 10.0) -> None:
        """
        Stop the queue manager gracefully.
        
        Args:
            timeout: Seconds to wait for workers to finish.
        """
        if not self._running:
            return
        
        logger.info("Stopping queue manager")
        
        # Stop autosave
        if self._autosave_task:
            self._autosave_task.cancel()
            try:
                await self._autosave_task
            except asyncio.CancelledError:
                pass
            self._autosave_task = None
        
        # Stop workers
        if self.workers:
            await self.workers.stop(timeout=timeout)
            self.workers = None
        
        # Final save
        if self.persistence:
            await self._save_all_runs()
            self.persistence.close()
        
        self._running = False
        logger.info("Queue manager stopped")
    
    async def submit(
        self,
        input_content: str,
        agent_name: str = "Assistant",
        priority: RunPriority = RunPriority.NORMAL,
        session_id: Optional[str] = None,
        workspace: Optional[str] = None,
        config: Optional[Dict[str, Any]] = None,
        run_id: Optional[str] = None,
        chat_history: Optional[List[Dict[str, str]]] = None,
    ) -> str:
        """
        Submit a new run to the queue.
        
        Args:
            input_content: The input/prompt for the agent.
            agent_name: Name of the agent to use.
            priority: Run priority.
            session_id: Session ID for grouping.
            workspace: Workspace path.
            config: Additional configuration.
            run_id: Optional specific run ID.
            chat_history: Previous chat messages for context continuity.
            
        Returns:
            The run ID.
        """
        run = QueuedRun(
            agent_name=agent_name,
            input_content=input_content,
            priority=priority,
            session_id=session_id or self._current_session_id,
            workspace=workspace or os.getcwd(),
            config=config or {},
            max_retries=self.config.default_max_retries,
            chat_history=chat_history or [],
        )
        
        if run_id:
            run.run_id = run_id
        
        # Submit to scheduler
        result_id = await self.scheduler.submit(run)
        
        # Persist
        if self.persistence:
            self.persistence.save_run(run)
        
        return result_id
    
    async def cancel(self, run_id: str) -> bool:
        """Cancel a run."""
        result = await self.scheduler.cancel(run_id)
        
        if result and self.persistence:
            run = self.scheduler.get_run(run_id)
            if run:
                self.persistence.save_run(run)
        
        return result
    
    async def retry(self, run_id: str) -> Optional[str]:
        """Retry a failed run."""
        new_id = await self.scheduler.retry(run_id)
        
        if new_id and self.persistence:
            run = self.scheduler.get_run(new_id)
            if run:
                self.persistence.save_run(run)
        
        return new_id
    
    async def pause(self, run_id: str) -> bool:
        """Pause a running run."""
        return await self.scheduler.pause(run_id)
    
    async def resume(self, run_id: str) -> bool:
        """Resume a paused run."""
        return await self.scheduler.resume(run_id)
    
    async def update_input(self, run_id: str, new_input: str) -> bool:
        """Update the input content of a queued run."""
        return await self.scheduler.update_input(run_id, new_input)
    
    def get_run(self, run_id: str) -> Optional[QueuedRun]:
        """Get a run by ID."""
        return self.scheduler.get_run(run_id)
    
    def get_queued(self) -> List[QueuedRun]:
        """Get all queued runs."""
        return self.scheduler.get_queued()
    
    def get_running(self) -> List[QueuedRun]:
        """Get all running runs."""
        return self.scheduler.get_running()
    
    def list_runs(
        self,
        state: Optional[RunState] = None,
        session_id: Optional[str] = None,
        limit: int = 100,
    ) -> List[QueuedRun]:
        """
        List runs with optional filters.
        
        For active runs, uses scheduler. For historical, uses persistence.
        """
        if state and state.is_terminal() and self.persistence:
            return self.persistence.list_runs(
                state=state,
                session_id=session_id,
                limit=limit,
            )
        
        # Get from scheduler
        runs = self.scheduler.get_all()
        
        if state:
            runs = [r for r in runs if r.state == state]
        if session_id:
            runs = [r for r in runs if r.session_id == session_id]
        
        return runs[:limit]
    
    async def clear_queue(self) -> int:
        """Clear all queued runs."""
        count = await self.scheduler.clear_queue()
        return count
    
    def get_stats(self) -> QueueStats:
        """Get queue statistics."""
        if self.persistence:
            return self.persistence.get_stats(self._current_session_id)
        
        # Calculate from scheduler
        queued = self.scheduler.get_queued()
        running = self.scheduler.get_running()
        
        return QueueStats(
            queued_count=len(queued),
            running_count=len(running),
        )
    
    # Session management
    
    def set_session(self, session_id: str) -> None:
        """Set the current session ID."""
        self._current_session_id = session_id
    
    def save_session_state(self, state: Dict[str, Any]) -> None:
        """Save session state."""
        if self.persistence and self._current_session_id:
            self.persistence.save_session(
                self._current_session_id,
                state=state,
            )
    
    def load_session_state(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Load session state."""
        if self.persistence:
            return self.persistence.load_session(session_id)
        return None
    
    def list_sessions(self, limit: int = 50) -> List[Dict[str, Any]]:
        """List recent sessions."""
        if self.persistence:
            return self.persistence.list_sessions(limit)
        return []
    
    # Internal methods
    
    async def _recover_runs(self) -> None:
        """Recover pending runs from persistence."""
        if not self.persistence:
            return
        
        # Mark interrupted runs as failed
        interrupted = self.persistence.mark_interrupted_as_failed()
        if interrupted:
            logger.warning(f"Marked {interrupted} interrupted runs as failed")
        
        # Load pending runs
        pending = self.persistence.load_pending_runs()
        if pending:
            logger.info(f"Recovering {len(pending)} pending runs")
            self.scheduler.load_runs(pending)
            
            for run in pending:
                self.persistence.mark_recovered(run.run_id)
    
    async def _save_all_runs(self) -> None:
        """Save all active runs to persistence."""
        if not self.persistence:
            return
        
        for run in self.scheduler.get_all():
            self.persistence.save_run(run)
    
    async def _autosave_loop(self) -> None:
        """Periodically save runs to persistence."""
        while True:
            try:
                await asyncio.sleep(self.config.autosave_interval_seconds)
                await self._save_all_runs()
                logger.debug("Autosaved queue state")
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Autosave error: {e}")
    
    def _wrap_complete_callback(self):
        """Wrap complete callback to include persistence."""
        async def wrapper(run_id: str, run: QueuedRun):
            # Persist
            if self.persistence:
                self.persistence.save_run(run)
            
            # Call user callback
            if self._on_complete:
                await self._on_complete(run_id, run)
        
        return wrapper
    
    def _wrap_error_callback(self):
        """Wrap error callback to include persistence."""
        async def wrapper(run_id: str, error: Exception):
            # Persist
            if self.persistence:
                run = self.scheduler.get_run(run_id)
                if run:
                    self.persistence.save_run(run)
            
            # Call user callback
            if self._on_error:
                await self._on_error(run_id, error)
        
        return wrapper
    
    @property
    def is_running(self) -> bool:
        """Whether the queue manager is running."""
        return self._running
    
    @property
    def queued_count(self) -> int:
        """Number of queued runs."""
        return self.scheduler.queued_count
    
    @property
    def running_count(self) -> int:
        """Number of running runs."""
        return self.scheduler.running_count
    
    @classmethod
    def get_tools_for_run(cls, run_id: str) -> list:
        """
        Get tools for a specific run from the registry.
        
        Falls back to default tools if no run-specific tools are registered.
        """
        return cls._tools_registry.get(run_id) or cls._tools_registry.get("default", [])
    
    @classmethod
    def register_tools(cls, run_id: str, tools: list) -> None:
        """Register tools for a specific run."""
        cls._tools_registry[run_id] = tools
    
    @classmethod
    def unregister_tools(cls, run_id: str) -> None:
        """Unregister tools for a specific run."""
        cls._tools_registry.pop(run_id, None)
