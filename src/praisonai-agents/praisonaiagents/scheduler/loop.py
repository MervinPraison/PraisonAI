"""
Schedule Loop for PraisonAI Agents.

Polls ScheduleRunner for due jobs and fires a callback.
"""

import logging
import threading
import time
from typing import Callable, Optional

from .runner import ScheduleRunner
from .store import FileScheduleStore

logger = logging.getLogger(__name__)


class ScheduleLoop:
    """Tick loop that polls a ScheduleRunner and fires due jobs.

    Runs on a **daemon thread** so it never blocks the caller and
    is automatically cleaned up on process exit.

    Example::

        from praisonaiagents.scheduler import ScheduleLoop

        def handle(job):
            print(f"Firing: {job.name} — {job.message}")

        loop = ScheduleLoop(on_trigger=handle, tick_seconds=30)
        loop.start()
        # … later …
        loop.stop()
    """

    def __init__(
        self,
        on_trigger: Callable,
        store: Optional[FileScheduleStore] = None,
        tick_seconds: float = 30.0,
    ):
        """
        Args:
            on_trigger: Called with each due ``ScheduleJob``.
            store: Schedule store to poll.  Defaults to the global
                   ``FileScheduleStore()``.
            tick_seconds: Seconds between polls (default 30).
        """
        self._on_trigger = on_trigger
        self._store = store or FileScheduleStore()
        self._runner = ScheduleRunner(self._store)
        self._tick = tick_seconds
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

    # ── Public API ──────────────────────────────────────────────────────

    @property
    def is_running(self) -> bool:
        """Whether the loop thread is alive."""
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        """Start the tick loop on a daemon thread.

        Calling ``start()`` when already running is a no-op.
        """
        if self.is_running:
            return

        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run, name="schedule-loop", daemon=True
        )
        self._thread.start()
        logger.info("ScheduleLoop started (tick=%ss)", self._tick)

    def stop(self, timeout: float = 5.0) -> None:
        """Signal the loop to stop and wait for the thread to exit.

        Args:
            timeout: Max seconds to wait for the thread to join.
        """
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=timeout)
            self._thread = None
        logger.info("ScheduleLoop stopped")

    # ── Internal ────────────────────────────────────────────────────────

    def _run(self) -> None:
        """Loop body executed on the daemon thread."""
        while not self._stop_event.is_set():
            try:
                due = self._runner.get_due_jobs()
                for job in due:
                    try:
                        self._on_trigger(job)
                        # Update last_run_at so the job won't re-fire
                        # until the next interval elapses.
                        job.last_run_at = time.time()
                        self._store.update(job)
                        self._emit_hook(job)
                    except Exception:
                        logger.exception(
                            "Error triggering schedule job %s (%s)",
                            job.name, job.id,
                        )
            except Exception:
                logger.exception("ScheduleLoop tick error")

            # Sleep in small increments so stop() is responsive.
            self._stop_event.wait(timeout=self._tick)

    def _emit_hook(self, job) -> None:
        """Best-effort emit of SCHEDULE_TRIGGER notification.

        Logs the trigger event.  Hook-aware callers (e.g. bots) can
        wire a proper ``HookRunner`` externally via the ``on_trigger``
        callback.
        """
        logger.debug(
            "SCHEDULE_TRIGGER: job=%s id=%s", job.name, job.id
        )
