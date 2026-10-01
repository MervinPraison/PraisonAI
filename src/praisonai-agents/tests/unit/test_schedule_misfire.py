"""
Unit tests for the scheduler misfire / missed-run policy.

Tests:
- scheduled_instant() returns the occurrence a due job is firing for
- is_misfire() is False without a grace window (backward-compatible)
- A recurring occurrence older than misfire_grace_seconds is recorded as
  ``missed`` and not claimed/fired (interval + cron)
- A recovery within the grace window still fires once (coalesce)
- A first run (never fired) always fires, never recorded missed
- misfire_grace_seconds round-trips through to_dict / from_dict and is omitted
  when unset
- The default store (ConfigYamlScheduleStore) applies the same policy
"""

import os
import tempfile
import time

import pytest

from praisonaiagents.scheduler.models import Schedule, ScheduleJob
from praisonaiagents.scheduler.store import FileScheduleStore
from praisonaiagents.scheduler.config_store import ConfigYamlScheduleStore
from praisonaiagents.scheduler.due import scheduled_instant, is_misfire


def _interval_job(name="job", every=60, grace=None, last_run_at=None):
    job = ScheduleJob(
        name=name,
        schedule=Schedule(kind="every", every_seconds=every),
        message="hi",
        misfire_grace_seconds=grace,
    )
    if last_run_at is not None:
        job.last_run_at = last_run_at
    return job


class TestScheduledInstant:
    def test_interval_missed_slot(self):
        # last run at t0; the first overdue slot is t0 + one interval — its age
        # measures how long the job has been overdue.
        t0 = 1000.0
        job = _interval_job(every=60, last_run_at=t0)
        instant = scheduled_instant(job, t0 + 60 * 5 + 3)
        assert instant == t0 + 60

    def test_interval_first_run_has_no_instant(self):
        job = _interval_job(every=60)  # never run
        assert scheduled_instant(job, time.time()) is None

    def test_interval_not_yet_elapsed(self):
        t0 = 1000.0
        job = _interval_job(every=60, last_run_at=t0)
        assert scheduled_instant(job, t0 + 30) is None


class TestIsMisfire:
    def test_no_grace_is_never_misfire(self):
        t0 = 1000.0
        job = _interval_job(every=60, last_run_at=t0, grace=None)
        # Even a very old slot is not a misfire without a grace window.
        assert is_misfire(job, t0 + 60 * 100) is False

    def test_stale_slot_is_misfire(self):
        t0 = 1000.0
        job = _interval_job(every=60, last_run_at=t0, grace=90)
        # Slot at t0+60, now is t0+300 → age 240 > 90 grace.
        assert is_misfire(job, t0 + 300) is True

    def test_fresh_slot_within_grace_is_not_misfire(self):
        t0 = 1000.0
        job = _interval_job(every=60, last_run_at=t0, grace=90)
        # Slot at t0+60, now is t0+70 → age 10 < 90 grace.
        assert is_misfire(job, t0 + 70) is False

    def test_first_run_never_misfire(self):
        job = _interval_job(every=60, grace=1)  # never run
        assert is_misfire(job, time.time()) is False

    def test_string_grace_does_not_raise(self):
        # A hand-edited quoted YAML value (``'90'``) reaching is_misfire as a
        # string must not raise TypeError and abort the claim pass — it is
        # coerced, so a genuinely stale slot is still detected.
        t0 = 1000.0
        job = _interval_job(every=60, last_run_at=t0, grace=90)
        job.misfire_grace_seconds = "90"  # simulate un-coerced legacy value
        assert is_misfire(job, t0 + 300) is True

    def test_non_numeric_grace_is_not_misfire(self):
        # A non-numeric junk value must fail safe to "not a misfire" rather
        # than raising and starving other due jobs in the same pass.
        t0 = 1000.0
        job = _interval_job(every=60, last_run_at=t0, grace=90)
        job.misfire_grace_seconds = "notanumber"
        assert is_misfire(job, t0 + 300) is False


class TestGraceCoercion:
    def test_quoted_grace_coerced_to_float(self):
        # from_dict must coerce a quoted YAML numeric to float so the later
        # age comparison never raises.
        d = _interval_job(every=60, grace=None).to_dict()
        d["misfire_grace_seconds"] = "3600"
        restored = ScheduleJob.from_dict(d)
        assert restored.misfire_grace_seconds == 3600.0
        assert isinstance(restored.misfire_grace_seconds, float)

    def test_junk_grace_coerced_to_none(self):
        d = _interval_job(every=60, grace=None).to_dict()
        d["misfire_grace_seconds"] = "not-a-number"
        restored = ScheduleJob.from_dict(d)
        assert restored.misfire_grace_seconds is None


class TestClaimMisfire:
    def test_stale_occurrence_recorded_missed_not_claimed(self):
        with tempfile.TemporaryDirectory() as d:
            store = FileScheduleStore(store_dir=d)
            t0 = time.time() - 10000
            job = _interval_job(every=60, grace=90)
            job.last_run_at = t0
            store.add(job)
            claimed = store.claim_due(time.time(), owner_id="A")
            # Not fired.
            assert claimed == []
            # Recorded as observable missed, not silently dropped.
            history = store.get_history(job_id=job.id)
            assert len(history) == 1
            assert history[0].status == "missed"
            # Schedule advanced so it is not re-seen as due immediately.
            reloaded = store.get(job.id)
            assert reloaded.last_run_at is not None
            assert reloaded.last_run_at > t0

    def test_within_grace_still_fires_once(self):
        with tempfile.TemporaryDirectory() as d:
            store = FileScheduleStore(store_dir=d)
            now = time.time()
            job = _interval_job(every=60, grace=300)
            job.last_run_at = now - 65  # one slot ago, age ~5s < grace
            store.add(job)
            claimed = store.claim_due(now, owner_id="A")
            assert len(claimed) == 1

    def test_first_run_fires_despite_grace(self):
        with tempfile.TemporaryDirectory() as d:
            store = FileScheduleStore(store_dir=d)
            job = _interval_job(every=60, grace=1)  # never run
            store.add(job)
            claimed = store.claim_due(time.time(), owner_id="A")
            assert len(claimed) == 1

    def test_no_grace_backward_compatible_fires(self):
        with tempfile.TemporaryDirectory() as d:
            store = FileScheduleStore(store_dir=d)
            job = _interval_job(every=60, grace=None)
            job.last_run_at = time.time() - 100000  # long downtime
            store.add(job)
            claimed = store.claim_due(time.time(), owner_id="A")
            # Unchanged behaviour: still fires once on recovery.
            assert len(claimed) == 1
            assert store.get_history(job_id=job.id) == []

    @pytest.mark.skipif(
        __import__("importlib").util.find_spec("croniter") is None,
        reason="croniter not installed",
    )
    def test_cron_stale_occurrence_recorded_missed(self):
        with tempfile.TemporaryDirectory() as d:
            store = FileScheduleStore(store_dir=d)
            # Daily 07:00 UTC; last run long ago, now well past a 07:00 slot.
            job = ScheduleJob(
                name="brief",
                schedule=Schedule(kind="cron", cron_expr="0 7 * * *", tz="UTC"),
                message="brief",
                misfire_grace_seconds=600,  # 10 min grace
            )
            job.last_run_at = time.time() - 3 * 86400
            store.add(job)
            claimed = store.claim_due(time.time(), owner_id="A")
            assert claimed == []
            history = store.get_history(job_id=job.id)
            assert len(history) == 1
            assert history[0].status == "missed"

    @pytest.mark.skipif(
        __import__("importlib").util.find_spec("croniter") is None,
        reason="croniter not installed",
    )
    def test_cron_first_run_fires_despite_stale_slot(self):
        # A never-run cron job first polled after its slot has aged past grace
        # must still fire its initial run — the first fire is not a recovered
        # recurrence to suppress.
        with tempfile.TemporaryDirectory() as d:
            store = FileScheduleStore(store_dir=d)
            job = ScheduleJob(
                name="brief",
                schedule=Schedule(kind="cron", cron_expr="0 7 * * *", tz="UTC"),
                message="brief",
                misfire_grace_seconds=600,
                # created far in the past so the first 07:00 slot is already
                # due; last_run_at left None → never run.
                created_at=time.time() - 3 * 86400,
            )
            store.add(job)
            claimed = store.claim_due(time.time(), owner_id="A")
            assert len(claimed) == 1
            # No missed record for a first run.
            assert store.get_history(job_id=job.id) == []


class TestSerialisation:
    def test_grace_round_trips(self):
        job = _interval_job(grace=120)
        restored = ScheduleJob.from_dict(job.to_dict())
        assert restored.misfire_grace_seconds == 120

    def test_grace_omitted_when_unset(self):
        job = _interval_job(grace=None)
        assert "misfire_grace_seconds" not in job.to_dict()


class TestConfigYamlMisfire:
    def test_stale_occurrence_recorded_missed(self):
        with tempfile.TemporaryDirectory() as d:
            store = ConfigYamlScheduleStore(
                config_path=os.path.join(d, "config.yaml")
            )
            job = _interval_job(every=60, grace=90)
            job.last_run_at = time.time() - 10000
            store.add(job)
            claimed = store.claim_due(time.time(), owner_id="A")
            assert claimed == []
            history = store.get_history(job_id=job.id)
            assert len(history) == 1
            assert history[0].status == "missed"

    def test_yaml_grace_round_trips_through_store(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "config.yaml")
            store = ConfigYamlScheduleStore(config_path=path)
            job = _interval_job(every=60, grace=120)
            store.add(job)
            # Reopen from disk and confirm the field survives serialisation.
            reopened = ConfigYamlScheduleStore(config_path=path)
            reloaded = reopened.get(job.id)
            assert reloaded is not None
            assert reloaded.misfire_grace_seconds == 120
