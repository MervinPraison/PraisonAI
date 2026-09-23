"""
Unit tests for atomic at-most-once job claim in the scheduler.

Tests:
- FileScheduleStore.claim_due() reserves due jobs and advances last_run_at
- A second claim by another owner does not re-claim a leased job
- Concurrent claims (threads) each get disjoint jobs — no double-fire
- complete() releases the lease
- Expired leases become claimable again (crash recovery)
- One-shot jobs (delete_after_run) are removed on claim
- Lease metadata round-trips through to_dict/from_dict
- ScheduleRunner.claim_due_jobs falls back to get_due_jobs without claim
"""

import os
import tempfile
import threading
import time

from praisonaiagents.scheduler.models import Schedule, ScheduleJob
from praisonaiagents.scheduler.store import FileScheduleStore
from praisonaiagents.scheduler.config_store import ConfigYamlScheduleStore
from praisonaiagents.scheduler.runner import ScheduleRunner


def _make_job(name="job", every=1):
    return ScheduleJob(
        name=name,
        schedule=Schedule(kind="every", every_seconds=every),
        message="hello",
    )


class TestClaimDue:
    def test_claim_returns_due_job_and_advances(self):
        with tempfile.TemporaryDirectory() as d:
            store = FileScheduleStore(store_dir=d)
            job = _make_job()
            store.add(job)
            now = time.time()
            claimed = store.claim_due(now, owner_id="A", lease_seconds=300)
            assert len(claimed) == 1
            assert claimed[0].id == job.id
            # last_run_at advanced → no longer due immediately
            reloaded = store.get(job.id)
            assert reloaded.last_run_at == now

    def test_second_owner_does_not_reclaim_leased_job(self):
        with tempfile.TemporaryDirectory() as d:
            store = FileScheduleStore(store_dir=d)
            store.add(_make_job())
            now = time.time()
            first = store.claim_due(now, owner_id="A", lease_seconds=300)
            assert len(first) == 1
            # Immediately after: same now, job leased by A and just advanced.
            second = store.claim_due(now, owner_id="B", lease_seconds=300)
            assert second == []

    def test_complete_releases_lease(self):
        with tempfile.TemporaryDirectory() as d:
            store = FileScheduleStore(store_dir=d)
            job = _make_job()
            store.add(job)
            now = time.time()
            store.claim_due(now, owner_id="A", lease_seconds=300)
            store.complete(job.id, owner_id="A")
            reloaded = store.get(job.id)
            assert getattr(reloaded, "_lease_until", 0.0) in (0.0, None)

    def test_expired_lease_is_reclaimable(self):
        with tempfile.TemporaryDirectory() as d:
            store = FileScheduleStore(store_dir=d)
            store.add(_make_job(every=1))
            t0 = time.time()
            store.claim_due(t0, owner_id="A", lease_seconds=5)
            # Later than both the interval and the lease window.
            t1 = t0 + 10
            reclaimed = store.claim_due(t1, owner_id="B", lease_seconds=5)
            assert len(reclaimed) == 1

    def test_one_shot_removed_on_claim(self):
        with tempfile.TemporaryDirectory() as d:
            store = FileScheduleStore(store_dir=d)
            job = ScheduleJob(
                name="once",
                schedule=Schedule(kind="every", every_seconds=1),
                message="hi",
                delete_after_run=True,
            )
            store.add(job)
            claimed = store.claim_due(time.time(), owner_id="A")
            assert len(claimed) == 1
            assert store.get(job.id) is None

    def test_concurrent_claims_no_double_fire(self):
        with tempfile.TemporaryDirectory() as d:
            store = FileScheduleStore(store_dir=d)
            for i in range(20):
                store.add(_make_job(name=f"job{i}"))
            now = time.time()
            results = []
            lock = threading.Lock()

            def worker(owner):
                claimed = store.claim_due(now, owner_id=owner, lease_seconds=300)
                with lock:
                    results.extend((owner, j.id) for j in claimed)

            threads = [
                threading.Thread(target=worker, args=(f"owner{n}",))
                for n in range(5)
            ]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

            claimed_ids = [jid for _, jid in results]
            # Every job claimed at most once across all owners.
            assert len(claimed_ids) == len(set(claimed_ids))
            # And all 20 due jobs were claimed exactly once in total.
            assert len(claimed_ids) == 20

    def test_failed_persist_does_not_return_claim(self):
        # If the atomic write fails the lease/last_run_at advance is not on
        # disk; returning the job would let the runner fire it while the next
        # poll re-reads the unchanged file and fires a duplicate. The claim
        # must be dropped (empty result) so it is retried cleanly.
        with tempfile.TemporaryDirectory() as d:
            store = FileScheduleStore(store_dir=d)
            job = _make_job()
            store.add(job)
            store._save = lambda: False
            claimed = store.claim_due(time.time(), owner_id="A", lease_seconds=300)
            assert claimed == []
            assert store._held_leases == {}

    def test_lease_round_trips_through_dict(self):
        job = _make_job()
        job._lease_until = 12345.0
        job._lease_owner = "A"
        restored = ScheduleJob.from_dict(job.to_dict())
        assert restored._lease_until == 12345.0
        assert restored._lease_owner == "A"

    def test_no_lease_omitted_from_dict(self):
        job = _make_job()
        d = job.to_dict()
        assert "lease_until" not in d
        assert "lease_owner" not in d


class TestBoundedRetirement:
    """Stop-condition (``max_runs`` / ``until``) lifecycle across claim+run."""

    def _make_bounded(self, **kw):
        return ScheduleJob(
            name="bounded",
            schedule=Schedule(kind="every", every_seconds=1),
            message="hi",
            **kw,
        )

    def test_claim_then_mark_run_counts_once(self):
        # Regression: claim_due increments run_count AND mark_run must not
        # double-count the same fire.
        with tempfile.TemporaryDirectory() as d:
            store = FileScheduleStore(store_dir=d)
            job = self._make_bounded(max_runs=3)
            store.add(job)
            runner = ScheduleRunner(store)
            claimed = runner.claim_due_jobs(owner_id="A")
            assert len(claimed) == 1
            runner.mark_run(claimed[0], status="succeeded")
            assert store.get(job.id).run_count == 1

    def test_max_runs_two_fires_exactly_twice(self):
        # A max_runs=2 job must survive the first fire and retire after the
        # second (it previously retired after one due to double counting).
        with tempfile.TemporaryDirectory() as d:
            store = FileScheduleStore(store_dir=d)
            job = self._make_bounded(max_runs=2)
            store.add(job)
            runner = ScheduleRunner(store)
            fires = 0
            t = time.time()
            for i in range(5):
                claimed = store.claim_due(t + i, owner_id="A", lease_seconds=0.5)
                for c in claimed:
                    fires += 1
                    runner.mark_run(c, status="succeeded")
            assert fires == 2
            assert store.get(job.id) is None

    def test_delete_after_run_equals_max_runs_one(self):
        with tempfile.TemporaryDirectory() as d:
            store = FileScheduleStore(store_dir=d)
            job = self._make_bounded(delete_after_run=True)
            store.add(job)
            runner = ScheduleRunner(store)
            claimed = runner.claim_due_jobs(owner_id="A")
            assert len(claimed) == 1
            runner.mark_run(claimed[0], status="succeeded")
            assert store.get(job.id) is None

    def test_expired_until_retires_without_firing(self):
        # A job whose ``until`` has already passed must be actively removed by
        # the claim path (not linger) and must NOT fire.
        with tempfile.TemporaryDirectory() as d:
            store = FileScheduleStore(store_dir=d)
            past = "2000-01-01T00:00:00+00:00"
            job = self._make_bounded(until=past)
            store.add(job)
            claimed = store.claim_due(time.time(), owner_id="A")
            assert claimed == []
            assert store.get(job.id) is None

    def test_future_until_still_fires(self):
        with tempfile.TemporaryDirectory() as d:
            store = FileScheduleStore(store_dir=d)
            future = "2999-01-01T00:00:00+00:00"
            job = self._make_bounded(until=future)
            store.add(job)
            claimed = store.claim_due(time.time(), owner_id="A")
            assert len(claimed) == 1
            assert store.get(job.id) is not None

    def test_invalid_until_fails_safe_and_retires(self):
        # A malformed ``until`` must not run forever: the job is not fired and
        # is retired by the claim path.
        with tempfile.TemporaryDirectory() as d:
            store = FileScheduleStore(store_dir=d)
            job = self._make_bounded(until="not-a-timestamp")
            store.add(job)
            claimed = store.claim_due(time.time(), owner_id="A")
            assert claimed == []
            assert store.get(job.id) is None

    def test_unbounded_job_persists_no_new_keys(self):
        job = _make_job()
        d = job.to_dict()
        assert "max_runs" not in d
        assert "until" not in d
        assert "run_count" not in d


class TestRunnerClaim:
    def test_runner_supports_atomic_claim(self):
        with tempfile.TemporaryDirectory() as d:
            store = FileScheduleStore(store_dir=d)
            runner = ScheduleRunner(store)
            assert runner.supports_atomic_claim() is True

    def test_runner_claim_due_jobs(self):
        with tempfile.TemporaryDirectory() as d:
            store = FileScheduleStore(store_dir=d)
            store.add(_make_job())
            runner = ScheduleRunner(store)
            claimed = runner.claim_due_jobs(owner_id="A")
            assert len(claimed) == 1
            # Second call at same time: already advanced, nothing due.
            again = runner.claim_due_jobs(owner_id="A")
            assert again == []

    def test_runner_falls_back_without_claim(self):
        class MinimalStore:
            def __init__(self):
                self._jobs = {}

            def list(self, agent_id=None):
                return list(self._jobs.values())

            def update(self, job):
                self._jobs[job.id] = job

            def remove(self, job_id):
                return self._jobs.pop(job_id, None) is not None

        store = MinimalStore()
        job = _make_job()
        store._jobs[job.id] = job
        runner = ScheduleRunner(store)
        assert runner.supports_atomic_claim() is False
        claimed = runner.claim_due_jobs(owner_id="A")
        assert len(claimed) == 1


class TestConfigYamlClaimDue:
    """The default store (``ConfigYamlScheduleStore``) must offer the same
    at-most-once atomic claim as the legacy ``FileScheduleStore``."""

    def _make_store(self, d):
        return ConfigYamlScheduleStore(config_path=os.path.join(d, "config.yaml"))

    def test_claim_returns_due_job_and_advances(self):
        with tempfile.TemporaryDirectory() as d:
            store = self._make_store(d)
            job = _make_job()
            store.add(job)
            now = time.time()
            claimed = store.claim_due(now, owner_id="A", lease_seconds=300)
            assert len(claimed) == 1
            assert claimed[0].id == job.id
            reloaded = store.get(job.id)
            assert reloaded.last_run_at == now

    def test_second_owner_does_not_reclaim_leased_job(self):
        with tempfile.TemporaryDirectory() as d:
            store = self._make_store(d)
            store.add(_make_job())
            now = time.time()
            first = store.claim_due(now, owner_id="A", lease_seconds=300)
            assert len(first) == 1
            second = store.claim_due(now, owner_id="B", lease_seconds=300)
            assert second == []

    def test_complete_releases_lease(self):
        with tempfile.TemporaryDirectory() as d:
            store = self._make_store(d)
            job = _make_job()
            store.add(job)
            now = time.time()
            store.claim_due(now, owner_id="A", lease_seconds=300)
            store.complete(job.id, owner_id="A")
            reloaded = store.get(job.id)
            assert getattr(reloaded, "_lease_until", 0.0) in (0.0, None)

    def test_expired_lease_is_reclaimable(self):
        with tempfile.TemporaryDirectory() as d:
            store = self._make_store(d)
            store.add(_make_job(every=1))
            t0 = time.time()
            store.claim_due(t0, owner_id="A", lease_seconds=5)
            t1 = t0 + 10
            reclaimed = store.claim_due(t1, owner_id="B", lease_seconds=5)
            assert len(reclaimed) == 1

    def test_one_shot_removed_on_claim(self):
        with tempfile.TemporaryDirectory() as d:
            store = self._make_store(d)
            job = ScheduleJob(
                name="once",
                schedule=Schedule(kind="every", every_seconds=1),
                message="hi",
                delete_after_run=True,
            )
            store.add(job)
            claimed = store.claim_due(time.time(), owner_id="A")
            assert len(claimed) == 1
            assert store.get(job.id) is None

    def test_concurrent_claims_no_double_fire(self):
        with tempfile.TemporaryDirectory() as d:
            store = self._make_store(d)
            for i in range(20):
                store.add(_make_job(name=f"job{i}"))
            now = time.time()
            results = []
            lock = threading.Lock()

            def worker(owner):
                claimed = store.claim_due(now, owner_id=owner, lease_seconds=300)
                with lock:
                    results.extend((owner, j.id) for j in claimed)

            threads = [
                threading.Thread(target=worker, args=(f"owner{n}",))
                for n in range(5)
            ]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

            claimed_ids = [jid for _, jid in results]
            assert len(claimed_ids) == len(set(claimed_ids))
            assert len(claimed_ids) == 20

    def test_separate_store_instances_do_not_double_fire(self):
        # Two independent store instances over the same config.yaml — the
        # closest single-process analogue of two gateway replicas.
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "config.yaml")
            seed = ConfigYamlScheduleStore(config_path=path)
            seed.add(_make_job())
            now = time.time()
            store_a = ConfigYamlScheduleStore(config_path=path)
            store_b = ConfigYamlScheduleStore(config_path=path)
            claimed_a = store_a.claim_due(now, owner_id="A", lease_seconds=300)
            claimed_b = store_b.claim_due(now, owner_id="B", lease_seconds=300)
            total = len(claimed_a) + len(claimed_b)
            assert total == 1

    def test_failed_persist_does_not_return_claim(self):
        with tempfile.TemporaryDirectory() as d:
            store = self._make_store(d)
            job = _make_job()
            store.add(job)
            store._save = lambda: False
            claimed = store.claim_due(time.time(), owner_id="A", lease_seconds=300)
            assert claimed == []
            assert store._held_leases == {}

    def test_runner_supports_atomic_claim_on_default_store(self):
        with tempfile.TemporaryDirectory() as d:
            store = self._make_store(d)
            runner = ScheduleRunner(store)
            assert runner.supports_atomic_claim() is True

    def test_runner_claim_due_jobs_on_default_store(self):
        with tempfile.TemporaryDirectory() as d:
            store = self._make_store(d)
            store.add(_make_job())
            runner = ScheduleRunner(store)
            claimed = runner.claim_due_jobs(owner_id="A")
            assert len(claimed) == 1
            again = runner.claim_due_jobs(owner_id="A")
            assert again == []
