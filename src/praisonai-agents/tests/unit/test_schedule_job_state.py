"""
Unit tests for the per-job durable scratchpad (JobStateStoreProtocol) on
``ConfigYamlScheduleStore``.

Covers:
- get_state returns {} when absent; set/get round-trip and persist across
  fresh store instances (config.yaml)
- clear_state and empty-state-clears semantics
- state is dropped when a job is removed (remove / remove_by_name)
- oversized state is rejected (prior kept)
- the store satisfies the core JobStateStoreProtocol
"""

import os
import tempfile

from praisonaiagents.scheduler.models import Schedule, ScheduleJob
from praisonaiagents.scheduler.config_store import ConfigYamlScheduleStore
from praisonaiagents.scheduler.protocols import JobStateStoreProtocol


def _cfg(d):
    return os.path.join(d, "config.yaml")


def _make_job(name="job", every=1):
    return ScheduleJob(
        name=name,
        schedule=Schedule(kind="every", every_seconds=every),
        message="hello",
    )


class TestJobState:
    def test_absent_returns_empty(self):
        with tempfile.TemporaryDirectory() as d:
            store = ConfigYamlScheduleStore(config_path=_cfg(d))
            assert store.get_state("nope") == {}

    def test_set_get_round_trip(self):
        with tempfile.TemporaryDirectory() as d:
            store = ConfigYamlScheduleStore(config_path=_cfg(d))
            store.set_state("j1", {"last_seen_pr": 4821})
            assert store.get_state("j1") == {"last_seen_pr": 4821}

    def test_persists_across_instances(self):
        with tempfile.TemporaryDirectory() as d:
            path = _cfg(d)
            store = ConfigYamlScheduleStore(config_path=path)
            store.set_state("j1", {"cursor": "abc"})
            fresh = ConfigYamlScheduleStore(config_path=path)
            assert fresh.get_state("j1") == {"cursor": "abc"}

    def test_get_returns_copy(self):
        with tempfile.TemporaryDirectory() as d:
            store = ConfigYamlScheduleStore(config_path=_cfg(d))
            store.set_state("j1", {"n": 1})
            got = store.get_state("j1")
            got["n"] = 999
            assert store.get_state("j1") == {"n": 1}

    def test_clear_state(self):
        with tempfile.TemporaryDirectory() as d:
            store = ConfigYamlScheduleStore(config_path=_cfg(d))
            store.set_state("j1", {"n": 1})
            store.clear_state("j1")
            assert store.get_state("j1") == {}

    def test_empty_state_clears(self):
        with tempfile.TemporaryDirectory() as d:
            store = ConfigYamlScheduleStore(config_path=_cfg(d))
            store.set_state("j1", {"n": 1})
            store.set_state("j1", {})
            assert store.get_state("j1") == {}

    def test_state_dropped_on_remove(self):
        with tempfile.TemporaryDirectory() as d:
            store = ConfigYamlScheduleStore(config_path=_cfg(d))
            job = _make_job()
            store.add(job)
            store.set_state(job.id, {"n": 1})
            assert store.remove(job.id) is True
            assert store.get_state(job.id) == {}

    def test_state_dropped_on_remove_by_name(self):
        with tempfile.TemporaryDirectory() as d:
            store = ConfigYamlScheduleStore(config_path=_cfg(d))
            job = _make_job(name="daily")
            store.add(job)
            store.set_state(job.id, {"n": 1})
            assert store.remove_by_name("daily") is True
            assert store.get_state(job.id) == {}

    def test_oversized_rejected_keeps_prior(self):
        with tempfile.TemporaryDirectory() as d:
            store = ConfigYamlScheduleStore(config_path=_cfg(d))
            store.set_state("j1", {"ok": 1})
            store.set_state("j1", {"big": "x" * (32 * 1024)})
            # oversized write rejected → prior state retained
            assert store.get_state("j1") == {"ok": 1}

    def test_job_state_key_absent_when_empty(self):
        with tempfile.TemporaryDirectory() as d:
            path = _cfg(d)
            store = ConfigYamlScheduleStore(config_path=path)
            store.add(_make_job())
            import yaml
            with open(path) as f:
                data = yaml.safe_load(f) or {}
            assert "job_state" not in data

    def test_satisfies_protocol(self):
        with tempfile.TemporaryDirectory() as d:
            store = ConfigYamlScheduleStore(config_path=_cfg(d))
            assert isinstance(store, JobStateStoreProtocol)
