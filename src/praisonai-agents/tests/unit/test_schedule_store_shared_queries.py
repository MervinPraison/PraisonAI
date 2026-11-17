"""G-30: the two schedule stores share one copy of their query methods.

Characterisation test (passes before and after): ``get``, ``get_by_name``,
``list``, ``complete`` and ``get_history`` behave the same on
``FileScheduleStore`` and ``ConfigYamlScheduleStore``.
"""

import time

import pytest

from praisonaiagents.scheduler.config_store import ConfigYamlScheduleStore
from praisonaiagents.scheduler.models import Schedule, ScheduleJob
from praisonaiagents.scheduler.store import FileScheduleStore


@pytest.fixture(params=["file", "config_yaml"])
def store(request, tmp_path):
    if request.param == "file":
        return FileScheduleStore(store_dir=str(tmp_path))
    return ConfigYamlScheduleStore(config_path=str(tmp_path / "config.yaml"))


def _job(name, agent_id="a1", principal=None):
    return ScheduleJob(name=name, message="hi", agent_id=agent_id, principal=principal,
                       schedule=Schedule(kind="every", every_seconds=60))


def test_lookup_and_filters(store):
    mine, theirs, other_agent = _job("daily", principal="u1"), _job("weekly", principal="u2"), _job("x", agent_id="a2")
    for job in (mine, theirs, other_agent):
        store.add(job)
    assert store.get(mine.id).name == "daily" and store.get("missing") is None
    assert store.get_by_name("daily").id == mine.id
    assert store.get_by_name("daily", principal="u2") is None  # owned by someone else
    assert store.get_by_name("nope") is None
    assert {j.id for j in store.list()} == {mine.id, theirs.id, other_agent.id}
    assert {j.id for j in store.list(agent_id="a1")} == {mine.id, theirs.id}
    assert [j.id for j in store.list(principal="u2")] == [theirs.id]


def test_complete_releases_only_the_owners_lease(store):
    job = _job("due")
    store.add(job)
    t0 = time.time() + 3600
    claimed = store.claim_due(now=t0, owner_id="w1", lease_seconds=300)
    assert [j.id for j in claimed] == [job.id]
    store.complete(job.id, owner_id="someone-else")
    # Due again 60 s later, but w1's 300 s lease still holds it.
    assert store.claim_due(now=t0 + 120, owner_id="w2") == []
    store.complete(job.id, owner_id="w1")
    store.complete("missing", owner_id="w1")  # no-op
    assert [j.id for j in store.claim_due(now=t0 + 120, owner_id="w2")] == [job.id]


def test_history_newest_first_filtered_and_limited(store):
    for i in range(3):
        store.log_run("j1", "succeeded", result=f"r{i}")
        time.sleep(0.002)
    store.log_run("j2", "failed", error="boom")
    assert [r.job_id for r in store.get_history()][:1] == ["j2"]
    assert [r.result for r in store.get_history(job_id="j1")] == ["r2", "r1", "r0"]
    assert len(store.get_history(limit=2)) == 2
