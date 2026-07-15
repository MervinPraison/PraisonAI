"""
Unit tests for the pluggable scheduler trigger provider.

Tests:
- SchedulerProviderProtocol is exported and runtime-checkable
- The built-in ScheduleLoop satisfies SchedulerProviderProtocol
- InProcessScheduleProvider is an alias of ScheduleLoop (backward-compatible)
- fire_due() claims and fires due jobs without an always-on thread
- start(on_due=...) lets an external caller drive *when* firing happens
"""

import tempfile
import time

from praisonaiagents.scheduler import (
    ScheduleLoop,
    InProcessScheduleProvider,
    SchedulerProviderProtocol,
)
from praisonaiagents.scheduler.models import Schedule, ScheduleJob
from praisonaiagents.scheduler.store import FileScheduleStore


def _make_job(name="job", every=1):
    return ScheduleJob(
        name=name,
        schedule=Schedule(kind="every", every_seconds=every),
        message="hello",
    )


class TestSchedulerProvider:
    def test_alias_is_schedule_loop(self):
        assert InProcessScheduleProvider is ScheduleLoop

    def test_loop_satisfies_provider_protocol(self):
        loop = ScheduleLoop(on_trigger=lambda job: None)
        assert isinstance(loop, SchedulerProviderProtocol)
        assert hasattr(loop, "fire_due")

    def test_fire_due_fires_due_jobs_without_thread(self):
        with tempfile.TemporaryDirectory() as d:
            store = FileScheduleStore(store_dir=d)
            job = _make_job()
            # Make it due in the past.
            job.last_run_at = time.time() - 10
            store.add(job)

            fired = []
            loop = ScheduleLoop(on_trigger=fired.append, store=store)
            # No thread started — an external provider drives firing directly.
            loop.fire_due()

            assert len(fired) == 1
            assert fired[0].id == job.id
            assert not loop.is_running

    def test_start_with_on_due_drives_firing(self):
        with tempfile.TemporaryDirectory() as d:
            store = FileScheduleStore(store_dir=d)
            loop = ScheduleLoop(
                on_trigger=lambda job: None, store=store, tick_seconds=0.05
            )

            ticks = []
            loop.start(on_due=lambda: ticks.append(1))
            try:
                # Wait for at least one tick via a short deadline.
                deadline = time.time() + 2.0
                while not ticks and time.time() < deadline:
                    time.sleep(0.05)
            finally:
                loop.stop()

            assert ticks, "on_due callback should be invoked by the loop thread"
