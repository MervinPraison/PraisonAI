"""
Kanban task dispatcher for gateway integration.

This module implements the background dispatcher that claims ready kanban tasks
and spawns agent runs to execute them. It integrates with the PraisonAI gateway
system and follows Hermes patterns for worker management.
"""

import asyncio
import logging
import os
import subprocess
import time
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)

# Global dispatcher state
_dispatcher_running = False
_dispatcher_task = None


class KanbanDispatcher:
    """Kanban task dispatcher that claims ready tasks and spawns workers."""
    
    def __init__(self, max_concurrent: int = 3, poll_interval: float = 5.0):
        """
        Initialize kanban dispatcher.
        
        Args:
            max_concurrent: Maximum concurrent task executions
            poll_interval: Seconds between task polling
        """
        self.max_concurrent = max_concurrent
        self.poll_interval = poll_interval
        self.running_tasks: Dict[str, subprocess.Popen] = {}
        self.worker_id = f"gateway_{os.getpid()}"
        
    def _get_kanban_store(self):
        """Get kanban store instance."""
        try:
            from praisonai.kanban.sqlite_store import SQLiteKanbanStore
            return SQLiteKanbanStore()
        except ImportError:
            logger.error("Kanban store not available")
            return None
    
    def _fire_hook_event(self, event_type: str, task_data: Dict[str, Any]):
        """Fire kanban hook events (when available)."""
        try:
            # Try to import and fire hook events from praisonaiagents
            from praisonaiagents.hooks import fire_hook
            fire_hook(event_type, task_data)
        except (ImportError, AttributeError):
            # Hook system not available, just log
            logger.debug(f"Hook event {event_type}: {task_data.get('task_id', 'unknown')}")
    
    async def dispatch_once(self) -> int:
        """
        Single dispatch cycle: claim ready tasks and spawn workers.
        
        Returns:
            Number of tasks spawned in this cycle
        """
        store = self._get_kanban_store()
        if not store:
            return 0
        
        # Clean up completed processes first
        self._cleanup_completed_tasks(store)
        
        # Promote dependency-driven tasks before claiming so a completed
        # parent advances its children to 'ready' on the next tick.
        self._promote_ready(store)
        
        # Check how many slots we have available
        available_slots = self.max_concurrent - len(self.running_tasks)
        if available_slots <= 0:
            logger.debug(f"No available slots (running: {len(self.running_tasks)})")
            return 0
        
        # Get ready tasks
        ready_tasks = store.list_tasks({'status': 'ready'})
        if not ready_tasks:
            logger.debug("No ready tasks found")
            return 0
        
        spawned = 0
        for task in ready_tasks[:available_slots]:
            try:
                # Try to claim the task atomically
                claimed = store.claim_task(task.id, self.worker_id)
                if not claimed:
                    logger.debug(f"Failed to claim task {task.id} (already claimed)")
                    continue
                
                # Spawn worker process
                success = await self._spawn_worker(task, store)
                if success:
                    spawned += 1
                    
                    # Fire claimed hook event
                    self._fire_hook_event('KANBAN_TASK_CLAIMED', {
                        'task_id': task.id,
                        'worker_id': self.worker_id,
                        'task': task.to_dict()
                    })
                else:
                    # Failed to spawn, release claim
                    store.release_claim(task.id, self.worker_id)
                    
            except Exception as e:
                logger.error(f"Error processing task {task.id}: {e}")
                # Release claim on error
                try:
                    store.release_claim(task.id, self.worker_id)
                except Exception as release_err:
                    logger.error(
                        "Failed to release claim for task %s (worker %s); task may be stuck "
                        "in 'claimed' state until manually released: %s",
                        task.id, self.worker_id, release_err,
                        exc_info=True,
                    )
        
        if spawned > 0:
            logger.info(f"Spawned {spawned} kanban task workers")
        
        return spawned
    
    def _promote_ready(self, store: Any) -> List[str]:
        """Promote dependency-driven tasks to 'ready' and fire move events.

        Runs once per dispatch tick before claiming. Delegates the promotion
        algorithm to the store's ``recompute_ready`` (when available) so that
        children whose parents are all terminal become claimable.

        Args:
            store: Kanban store instance.

        Returns:
            List of task IDs promoted to 'ready' this tick.
        """
        recompute = getattr(store, "recompute_ready", None)
        if not callable(recompute):
            return []

        try:
            promoted = recompute() or []
        except Exception as e:
            logger.error(f"Error recomputing ready tasks: {e}")
            return []

        for task_id in promoted:
            try:
                task = store.get_task(task_id)
            except Exception:
                task = None
            self._fire_hook_event('KANBAN_TASK_MOVED', {
                'task_id': task_id,
                'to_status': 'ready',
                'task': task.to_dict() if task and hasattr(task, 'to_dict') else {},
            })

        if promoted:
            logger.info(f"Promoted {len(promoted)} kanban task(s) to ready")

        return promoted

    async def _spawn_worker(self, task: Any, store: Any) -> bool:
        """
        Spawn a worker process for the task.
        
        Args:
            task: Task object to execute
            store: Kanban store instance
            
        Returns:
            True if worker was spawned successfully
        """
        try:
            # Prepare environment variables
            env = os.environ.copy()
            env.update({
                'PRAISONAI_KANBAN_TASK': task.id,
                'PRAISONAI_KANBAN_BOARD': task.board,
                'PRAISONAI_KANBAN_WORKER': self.worker_id,
            })
            
            # Build command to execute task
            # This could be configurable, but for now use a simple approach
            cmd = self._build_execution_command(task)
            
            logger.info(f"Spawning worker for task {task.id}: {' '.join(cmd)}")
            
            # Start process with output redirect to avoid deadlock
            import tempfile
            with tempfile.NamedTemporaryFile(mode='w+', delete=False, suffix='.log') as temp_log:
                temp_log_path = temp_log.name
            
            with open(temp_log_path, 'w') as log_handle:
                process = subprocess.Popen(
                    cmd,
                    env=env,
                    stdout=log_handle,
                    stderr=subprocess.STDOUT,
                    text=True
                )
            # parent FD closed here; child still has its duped copy
            
            # Store log path for later cleanup
            if not hasattr(self, '_temp_logs'):
                self._temp_logs = {}
            self._temp_logs[task.id] = temp_log_path
            
            # Track the running task
            self.running_tasks[task.id] = process
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to spawn worker for task {task.id}: {e}")
            return False
    
    def _build_execution_command(self, task: Any) -> List[str]:
        """
        Build the command to execute a kanban task.
        
        This is a simplified implementation. In a full system, this would:
        1. Parse task.body for specific execution instructions
        2. Route to different executors based on task metadata
        3. Support various agent configurations
        
        Args:
            task: Task to build command for
            
        Returns:
            Command as list of strings
        """
        # Default: use praisonai agent with the task as a prompt
        return [
            'praisonai',
            'agent',
            'run',
            '--name', f'kanban_worker_{task.id}',
            '--prompt', f'Task: {task.title}\n\nDetails: {task.body}',
            '--tools', 'kanban_heartbeat,kanban_comment',
            '--output-mode', 'quiet'
        ]
    
    def _cleanup_completed_tasks(self, store: Any):
        """
        Clean up completed task processes and update their status.
        
        Args:
            store: Kanban store instance
        """
        completed = []
        
        for task_id, process in self.running_tasks.items():
            poll_result = process.poll()
            
            if poll_result is not None:
                # Process completed
                completed.append(task_id)
                
                try:
                    # Get return code
                    return_code = process.returncode
                    
                    # Read output from temp log file
                    stdout_data = ""
                    if hasattr(self, '_temp_logs') and task_id in self._temp_logs:
                        try:
                            with open(self._temp_logs[task_id], 'r') as f:
                                stdout_data = f.read()
                        except Exception as e:
                            logger.warning(f"Failed to read log for task {task_id}: {e}")
                            stdout_data = f"<log read error: {e}>"
                    else:
                        stdout_data = "<no log available>"
                    
                    # Update task based on exit code
                    if return_code == 0:
                        # Success - mark as done
                        store.move_task(task_id, 'done')
                        store.add_comment(
                            task_id, 
                            self.worker_id, 
                            f"Task completed successfully\n\nOutput:\n{stdout_data[:500]}"
                        )
                        
                        # Fire completion hook
                        task = store.get_task(task_id)
                        self._fire_hook_event('KANBAN_TASK_COMPLETED', {
                            'task_id': task_id,
                            'worker_id': self.worker_id,
                            'return_code': return_code,
                            'task': task.to_dict() if task else {}
                        })
                        
                        logger.info(f"Task {task_id} completed successfully")
                    else:
                        # Failed - mark as blocked
                        store.move_task(task_id, 'blocked')
                        store.add_comment(
                            task_id,
                            self.worker_id,
                            f"Task failed with exit code {return_code}\n\nOutput:\n{stdout_data[:500]}"
                        )
                        
                        # Fire failure hook
                        task = store.get_task(task_id)
                        self._fire_hook_event('KANBAN_TASK_FAILED', {
                            'task_id': task_id,
                            'worker_id': self.worker_id,
                            'return_code': return_code,
                            'error': stdout_data[:500],
                            'task': task.to_dict() if task else {}
                        })
                        
                        logger.warning(f"Task {task_id} failed with code {return_code}")
                
                except Exception as e:
                    logger.error(f"Error processing completed task {task_id}: {e}")
                    # Release claim as fallback
                    try:
                        store.release_claim(task_id, self.worker_id)
                    except Exception as release_err:
                        logger.error(
                            "Failed to release claim during cleanup for task %s: %s",
                            task_id, release_err,
                            exc_info=True,
                        )
        
        # Remove completed tasks from tracking and clean up temp logs
        for task_id in completed:
            del self.running_tasks[task_id]
            
            # Clean up temporary log file
            if hasattr(self, '_temp_logs') and task_id in self._temp_logs:
                try:
                    import os
                    os.unlink(self._temp_logs[task_id])
                except Exception as e:
                    logger.warning(f"Failed to cleanup temp log for task {task_id}: {e}")
                finally:
                    del self._temp_logs[task_id]
    
    async def run_forever(self):
        """
        Run the dispatcher loop forever.
        """
        logger.info(f"Starting kanban dispatcher (max_concurrent={self.max_concurrent})")
        
        while True:
            try:
                await self.dispatch_once()
                await asyncio.sleep(self.poll_interval)
                
            except asyncio.CancelledError:
                logger.info("Kanban dispatcher cancelled")
                break
            except Exception as e:
                logger.error(f"Dispatcher error: {e}")
                await asyncio.sleep(self.poll_interval)
        
        # Cleanup on exit
        await self._shutdown()
    
    async def _shutdown(self):
        """Clean shutdown - wait for running tasks."""
        if self.running_tasks:
            logger.info(f"Waiting for {len(self.running_tasks)} running tasks to complete...")
            
            # Give tasks 30 seconds to complete gracefully
            timeout = 30
            start_time = time.time()
            
            while self.running_tasks and (time.time() - start_time) < timeout:
                store = self._get_kanban_store()
                if store:
                    self._cleanup_completed_tasks(store)
                await asyncio.sleep(1)
            
            # Force terminate remaining tasks
            for task_id, process in self.running_tasks.items():
                logger.warning(f"Force terminating task {task_id}")
                try:
                    process.terminate()
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    logger.warning(f"Task {task_id} did not terminate in 5s; sending SIGKILL")
                    try:
                        process.kill()
                    except OSError as kill_err:
                        logger.error(f"Failed to kill task {task_id}: {kill_err}")
                except OSError as os_err:
                    logger.error(f"OS error while terminating task {task_id}: {os_err}")
                    try:
                        process.kill()
                    except OSError as kill_err:
                        logger.error(f"Failed to kill task {task_id}: {kill_err}")
                # KeyboardInterrupt, SystemExit, CancelledError now propagate as intended
            
            self.running_tasks.clear()
        
        logger.info("Kanban dispatcher shutdown complete")


# Global dispatcher management functions

async def start_kanban_dispatcher(max_concurrent: int = 3, poll_interval: float = 5.0):
    """
    Start the global kanban dispatcher.
    
    Args:
        max_concurrent: Maximum concurrent task executions
        poll_interval: Seconds between polling cycles
    """
    global _dispatcher_running, _dispatcher_task
    
    if _dispatcher_running:
        logger.warning("Kanban dispatcher already running")
        return
    
    # Check if disabled by environment
    if not _is_dispatcher_enabled():
        logger.info("Kanban dispatcher disabled by PRAISONAI_KANBAN_DISPATCH=0")
        return
    
    dispatcher = KanbanDispatcher(max_concurrent, poll_interval)
    
    _dispatcher_task = asyncio.create_task(dispatcher.run_forever())
    _dispatcher_running = True
    
    logger.info("Kanban dispatcher started")


async def stop_kanban_dispatcher():
    """Stop the global kanban dispatcher."""
    global _dispatcher_running, _dispatcher_task
    
    if not _dispatcher_running or _dispatcher_task is None:
        return
    
    _dispatcher_task.cancel()
    
    try:
        await _dispatcher_task
    except asyncio.CancelledError:
        pass
    
    _dispatcher_running = False
    _dispatcher_task = None
    
    logger.info("Kanban dispatcher stopped")


def is_dispatcher_running() -> bool:
    """Check if the kanban dispatcher is running."""
    return _dispatcher_running


def _is_dispatcher_enabled() -> bool:
    """Check if kanban dispatcher is enabled via environment variable."""
    return os.environ.get('PRAISONAI_KANBAN_DISPATCH', '1').strip().lower() not in ('0', 'false', 'no')


# Manual dispatch function for CLI/testing

async def dispatch_once(max_spawn: int = 3) -> int:
    """
    Manually trigger a single dispatch cycle.
    
    Args:
        max_spawn: Maximum tasks to spawn in this cycle
        
    Returns:
        Number of tasks spawned
    """
    dispatcher = KanbanDispatcher(max_spawn)
    return await dispatcher.dispatch_once()