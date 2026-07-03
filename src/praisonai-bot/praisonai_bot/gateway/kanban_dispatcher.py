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
    
    def __init__(
        self,
        max_concurrent: int = 3,
        poll_interval: float = 5.0,
        claim_ttl_seconds: Optional[int] = None,
        stale_timeout_seconds: Optional[int] = None,
    ):
        """
        Initialize kanban dispatcher.
        
        Args:
            max_concurrent: Maximum concurrent task executions
            poll_interval: Seconds between task polling
            claim_ttl_seconds: Claim lease duration; reclaimable after expiry.
                Defaults to PRAISONAI_KANBAN_CLAIM_TTL (900s).
            stale_timeout_seconds: Heartbeat staleness threshold for reclaim.
                Defaults to PRAISONAI_KANBAN_STALE_TIMEOUT (1800s).
        """
        self.max_concurrent = max_concurrent
        self.poll_interval = poll_interval
        self.claim_ttl_seconds = (
            claim_ttl_seconds
            if claim_ttl_seconds is not None
            else _env_int('PRAISONAI_KANBAN_CLAIM_TTL', 900)
        )
        self.stale_timeout_seconds = (
            stale_timeout_seconds
            if stale_timeout_seconds is not None
            else _env_int('PRAISONAI_KANBAN_STALE_TIMEOUT', 1800)
        )
        self.running_tasks: Dict[str, subprocess.Popen] = {}
        self._task_runs: Dict[str, int] = {}  # task_id -> open run_id
        self.worker_id = f"gateway_{os.getpid()}"

    def _close_run_safe(self, store, run_id, outcome, *, summary=None, metadata=None, error=None) -> bool:
        """Close a run, swallowing errors so dispatch stays resilient.

        Returns True when the run was closed, False on a transient store error
        so the caller can keep tracking the open run id and retry the close
        on a later cycle instead of leaving stale active-run state behind.
        """
        try:
            store.close_run(run_id, outcome, summary=summary, metadata=metadata, error=error)
            return True
        except Exception as e:
            logger.warning(f"Failed to close run {run_id} ({outcome}): {e}")
            return False

    def _record_failure_safe(self, store, task_id, *, error=None):
        """Record a failure / circuit-breaker check, swallowing errors.

        Returns a tri-state:
            True  -> task was auto-blocked (circuit broken)
            False -> below the retry limit; safe to release for retry
            None  -> failure accounting did NOT persist; do not blindly retry
        """
        try:
            return store.record_failure(task_id, error=error)
        except Exception as e:
            logger.warning(f"Failed to record failure for task {task_id}: {e}")
            return None
        
    def _retry_pending_run_closes(self, store):
        """Retry closing runs whose close failed transiently on a prior cycle.

        A run id stays in ``_task_runs`` after its task leaves ``running_tasks``
        only when ``_close_run_safe`` returned False (transient store error).
        Those entries would otherwise never be revisited until shutdown, leaving
        the run open and ``tasks.current_run_id`` stale. Close them as failed
        (the worker already exited) and forget the id once the close persists.
        """
        if not self._task_runs:
            return
        for task_id in list(self._task_runs.keys()):
            if task_id in self.running_tasks:
                # Still active; its close is handled by the per-process loop.
                continue
            run_id = self._task_runs.get(task_id)
            if run_id is None:
                self._task_runs.pop(task_id, None)
                continue
            if self._close_run_safe(
                store, run_id, 'failed',
                error='Run close retried after a prior transient store error',
            ):
                self._task_runs.pop(task_id, None)

    def _get_kanban_store(self):
        """Get kanban store instance."""
        try:
            from praisonai_bot.kanban.sqlite_store import SQLiteKanbanStore
            return SQLiteKanbanStore()
        except ImportError:
            logger.error("Kanban store not available")
            return None
    
    def _kanban_event_id(self, event_name: str) -> str:
        """Resolve a HookEvent name to its canonical event id.

        Maps an enum member name (e.g. ``"KANBAN_TASK_MOVED"``) to its
        canonical value (e.g. ``"kanban_task_moved"``) so hook subscribers
        listening on the real event id receive it. Falls back to the
        provided name if the hooks package is unavailable.

        Args:
            event_name: HookEvent member name.

        Returns:
            Canonical event id string, or ``event_name`` on failure.
        """
        try:
            from praisonaiagents.hooks.types import HookEvent
            return HookEvent[event_name].value
        except Exception:
            return event_name

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

        # Reclaim stale/crashed claims before dispatching new work so that
        # tasks stranded by dead workers return to 'ready' and get re-dispatched.
        self._reclaim_stale_claims(store)
        
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
                # Try to claim the task atomically with a lease + owner PID.
                claimed = self._claim_task(store, task)
                if not claimed:
                    logger.debug(f"Failed to claim task {task.id} (already claimed)")
                    continue
                
                # Open a run (attempt) for this claim so failures/retries
                # have a durable, structured record. If we cannot create the
                # run row, do not spawn: release the claim and skip so the
                # attempt is never left without durable history.
                try:
                    run_id = store.start_run(task.id, profile=self.worker_id)
                except Exception as run_err:
                    logger.warning(f"Failed to start run for task {task.id}: {run_err}")
                    try:
                        store.release_claim(task.id, self.worker_id)
                    except Exception as release_err:
                        logger.error(
                            "Failed to release claim after run-start failure for %s: %s",
                            task.id, release_err, exc_info=True,
                        )
                    continue

                # Spawn worker process
                success = await self._spawn_worker(task, store)
                if not success:
                    # Failed to spawn: close run as failed, count it, and only
                    # release the claim for retry when the failure was recorded
                    # AND the task was not circuit-broken.
                    self._close_run_safe(
                        store, run_id, 'failed',
                        error='Failed to spawn worker process'
                    )
                    circuit_broken = self._record_failure_safe(
                        store, task.id, error='Failed to spawn worker process'
                    )
                    if circuit_broken is False:
                        store.release_claim(task.id, self.worker_id)
                    continue

                # Worker is now running. From here on we MUST NOT release the
                # claim on error: doing so would return the task to 'ready' and
                # let another dispatcher spawn a duplicate while this worker is
                # still executing. Post-spawn bookkeeping is therefore isolated.
                spawned += 1
                self._task_runs[task.id] = run_id
                try:
                    # Record the spawned worker's PID against the claim so the
                    # reclaim loop can detect a crashed/killed worker.
                    self._record_worker_pid(store, task.id)

                    # Fire claimed hook event
                    self._fire_hook_event('KANBAN_TASK_CLAIMED', {
                        'task_id': task.id,
                        'worker_id': self.worker_id,
                        'run_id': run_id,
                        'task': task.to_dict()
                    })
                except Exception as post_spawn_err:
                    # Never release the claim for an already-running worker.
                    logger.error(
                        "Post-spawn bookkeeping failed for task %s (worker still "
                        "running); leaving claim intact: %s",
                        task.id, post_spawn_err,
                        exc_info=True,
                    )
            except Exception as e:
                logger.error(f"Error processing task {task.id}: {e}")
                # Only release the claim if we never spawned a worker for it.
                # If a worker is already running, releasing would risk a
                # duplicate run; the reclaim loop will recover it if it dies.
                if task.id in self.running_tasks:
                    logger.warning(
                        "Task %s has a running worker; not releasing claim despite error",
                        task.id,
                    )
                    continue
                # Release claim on error (no worker spawned)
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
            task_dict = task.to_dict() if task and hasattr(task, 'to_dict') else None
            if task_dict is None:
                # Promotion already committed; if we can't read the task back,
                # skip emitting an event with an empty payload so consumers
                # never receive a moved event for a task they can't resolve.
                logger.debug(
                    "Promoted task %s could not be read back; skipping move event",
                    task_id,
                )
                continue
            self._fire_hook_event(self._kanban_event_id('KANBAN_TASK_MOVED'), {
                'task_id': task_id,
                'to_status': 'ready',
                'task': task_dict,
            })

        if promoted:
            logger.info(f"Promoted {len(promoted)} kanban task(s) to ready")

        return promoted

    def _claim_task(self, store: Any, task: Any) -> bool:
        """Claim a task with a lease, falling back for older stores."""
        try:
            return store.claim_task(
                task.id, self.worker_id,
                ttl_seconds=self.claim_ttl_seconds,
                worker_pid=os.getpid(),
            )
        except TypeError:
            # Backward compatibility with stores lacking the lease signature.
            return store.claim_task(task.id, self.worker_id)

    def _record_worker_pid(self, store: Any, task_id: str):
        """Associate the spawned worker's PID with the claim for liveness checks."""
        process = self.running_tasks.get(task_id)
        if process is None or not hasattr(store, 'heartbeat'):
            return
        try:
            self._set_worker_pid(store, task_id, process.pid)
        except Exception as e:
            logger.debug(f"Could not record worker PID for task {task_id}: {e}")

    def _set_worker_pid(self, store: Any, task_id: str, pid: int):
        """Best-effort direct update of worker_pid on the claim row."""
        get_conn = getattr(store, '_get_connection', None)
        if get_conn is None:
            return
        from datetime import datetime, timezone
        with get_conn() as conn:
            conn.execute(
                "UPDATE tasks SET worker_pid = ?, last_heartbeat_at = ? "
                "WHERE id = ? AND claim_lock = ?",
                (pid, datetime.now(timezone.utc).isoformat(), task_id, self.worker_id),
            )

    def _reclaim_stale_claims(self, store: Any):
        """Sweep running tasks and reclaim those stranded by dead/stale workers."""
        reclaim = getattr(store, 'reclaim_stale_claims', None)
        if reclaim is None:
            return
        try:
            reclaimed = reclaim(stale_timeout_seconds=self.stale_timeout_seconds)
        except TypeError:
            reclaimed = reclaim()
        except Exception as e:
            logger.error(f"Error during stale-claim reclamation: {e}")
            return

        for task_id in reclaimed or []:
            logger.warning(f"Reclaimed stale kanban task {task_id} back to 'ready'")
            self._fire_hook_event('KANBAN_TASK_RECLAIMED', {
                'task_id': task_id,
                'worker_id': self.worker_id,
            })

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
        # Default: use praisonai-code run with the task as a prompt
        import shutil
        import sys

        runner = shutil.which("praisonai-code") or sys.executable
        if runner == sys.executable:
            return [
                runner,
                "-m",
                "praisonai_code",
                "run",
                "--prompt",
                f'Task: {task.title}\n\nDetails: {task.body}',
            ]
        return [
            runner,
            "run",
            "--prompt",
            f'Task: {task.title}\n\nDetails: {task.body}',
        ]
    
    def _cleanup_completed_tasks(self, store: Any):
        """
        Clean up completed task processes and update their status.
        
        Args:
            store: Kanban store instance
        """
        # Retry any run closes that did not persist on a previous cycle. Those
        # run ids are retained in _task_runs but their task is no longer in
        # running_tasks, so the per-process loop below would never revisit them
        # and the open run / stale current_run_id would linger until shutdown.
        self._retry_pending_run_closes(store)

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
                    
                    # Peek (do not pop) the open run id. We only forget it once
                    # the run is durably closed so a transient close failure does
                    # not leave a stale current_run_id we can no longer retry.
                    run_id = self._task_runs.get(task_id)
                    
                    # Update task based on exit code
                    if return_code == 0:
                        # Success - mark as done FIRST so the terminal transition
                        # is the durable commit. If move_task fails the task stays
                        # claimed (not released for retry), avoiding a duplicate
                        # run of an already-successful worker.
                        # move_task to a terminal status clears the claim_lock
                        # so the finished task is no longer shown as owned.
                        store.move_task(task_id, 'done')
                        # Now record the completed run. Forget the run id only
                        # when the close persists; otherwise retry on next cycle.
                        if run_id is not None:
                            if self._close_run_safe(
                                store, run_id, 'completed',
                                summary=stdout_data[:500].strip(),
                                metadata={'return_code': return_code},
                            ):
                                self._task_runs.pop(task_id, None)
                        else:
                            self._task_runs.pop(task_id, None)
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
                            'run_id': run_id,
                            'task': task.to_dict() if task else {}
                        })
                        
                        logger.info(f"Task {task_id} completed successfully")
                    else:
                        # Failed - close run as failed, count it, circuit-break.
                        # Forget the run id only once the close persists so a
                        # transient store error is retried on a later cycle.
                        error_text = f"exit code {return_code}: {stdout_data[:500]}"
                        if run_id is not None:
                            if self._close_run_safe(
                                store, run_id, 'failed',
                                metadata={'return_code': return_code},
                                error=error_text,
                            ):
                                self._task_runs.pop(task_id, None)
                        else:
                            self._task_runs.pop(task_id, None)
                        circuit_broken = self._record_failure_safe(
                            store, task_id, error=error_text
                        )
                        if circuit_broken is True:
                            # Task already auto-blocked by record_failure
                            store.add_comment(
                                task_id,
                                self.worker_id,
                                f"Auto-blocked after repeated failures (exit code "
                                f"{return_code})\n\nLast output:\n{stdout_data[:500]}"
                            )
                        elif circuit_broken is False:
                            # Below the retry limit: release so it can be retried
                            store.add_comment(
                                task_id,
                                self.worker_id,
                                f"Task attempt failed with exit code {return_code} "
                                f"(will retry)\n\nOutput:\n{stdout_data[:500]}"
                            )
                            try:
                                store.release_claim(task_id, self.worker_id)
                            except Exception as release_err:
                                logger.warning(
                                    f"Failed to release claim for retry of {task_id}: {release_err}"
                                )
                        else:
                            # Failure accounting did not persist: do NOT blindly
                            # release for retry, which could bypass the circuit
                            # breaker indefinitely. Leave the claim in place.
                            store.add_comment(
                                task_id,
                                self.worker_id,
                                f"Task attempt failed with exit code {return_code}, "
                                f"but failure accounting did not persist; not "
                                f"auto-releasing for retry.\n\nOutput:\n{stdout_data[:500]}"
                            )
                        
                        # Fire failure hook
                        task = store.get_task(task_id)
                        self._fire_hook_event('KANBAN_TASK_FAILED', {
                            'task_id': task_id,
                            'worker_id': self.worker_id,
                            'return_code': return_code,
                            'error': stdout_data[:500],
                            'run_id': run_id,
                            'circuit_broken': circuit_broken,
                            'task': task.to_dict() if task else {}
                        })
                        
                        logger.warning(
                            f"Task {task_id} failed with code {return_code} "
                            f"(circuit_broken={circuit_broken})"
                        )
                
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
            store = self._get_kanban_store()
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

                # Close any open run for the interrupted attempt so we do not
                # leave dangling task_runs rows / stale current_run_id pointers.
                run_id = self._task_runs.pop(task_id, None)
                if store is not None and run_id is not None:
                    self._close_run_safe(
                        store, run_id, 'failed',
                        error='Dispatcher shutdown terminated worker before completion',
                    )

            self.running_tasks.clear()
            self._task_runs.clear()
        
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


def _env_int(name: str, default: int) -> int:
    """Read a positive integer from the environment, falling back to default."""
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        value = int(raw)
        return value if value > 0 else default
    except (ValueError, TypeError):
        return default


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