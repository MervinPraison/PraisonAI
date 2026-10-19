"""
Regression tests for FileScheduleStore persistence (issue #5899).

- Run history from two stores on the same dir is merged, not last-writer-wins.
- A failed save from add/update/remove raises, keeps memory consistent with
  disk, and does not fire lifecycle hooks.
"""

import os
from unittest import mock

import pytest

from praisonaiagents.scheduler import store as store_mod
from praisonaiagents.scheduler.models import Schedule, ScheduleJob
from praisonaiagents.scheduler.store import FileScheduleStore


def _make_job(name="job"):
    return ScheduleJob(
        name=name,
        schedule=Schedule(kind="every", every_seconds=60),
        message="hello",
    )


def test_history_not_lost_across_stores(tmp_path):
    d = str(tmp_path)
    a = FileScheduleStore(store_dir=d)
    b = FileScheduleStore(store_dir=d)
    a.log_run("j1", "succeeded", job_name="n1")
    b.log_run("j2", "succeeded", job_name="n2")
    ids = [r.job_id for r in FileScheduleStore(store_dir=d).get_history()]
    assert ids == ["j2", "j1"]


def test_history_respects_max_after_reload(tmp_path):
    d = str(tmp_path)
    a = FileScheduleStore(store_dir=d, max_history=2)
    b = FileScheduleStore(store_dir=d, max_history=2)
    a.log_run("j1", "succeeded")
    b.log_run("j2", "succeeded")
    a.log_run("j3", "succeeded")
    assert [r.job_id for r in a.get_history()] == ["j3", "j2"]


def _fail_replace(*args, **kwargs):
    raise OSError("disk full")


def test_add_failed_save_raises_and_rolls_back(tmp_path):
    d = str(tmp_path)
    s = FileScheduleStore(store_dir=d)
    with mock.patch("praisonaiagents.utils.atomic_io.os.replace", _fail_replace), \
            mock.patch.object(store_mod, "emit_schedule_add") as emit:
        with pytest.raises(OSError):
            s.add(_make_job())
        emit.assert_not_called()
    assert s.list() == []
    assert FileScheduleStore(store_dir=d).list() == []
    assert not [f for f in os.listdir(d) if f.endswith(".tmp")]


def test_update_failed_save_restores_previous(tmp_path):
    d = str(tmp_path)
    s = FileScheduleStore(store_dir=d)
    job = _make_job()
    s.add(job)
    changed = ScheduleJob.from_dict(job.to_dict())
    changed.message = "changed"
    with mock.patch("praisonaiagents.utils.atomic_io.os.replace", _fail_replace):
        with pytest.raises(OSError):
            s.update(changed)
    assert s.get(job.id).message == "hello"


def test_remove_failed_save_keeps_job(tmp_path):
    d = str(tmp_path)
    s = FileScheduleStore(store_dir=d)
    job = _make_job()
    s.add(job)
    with mock.patch("praisonaiagents.utils.atomic_io.os.replace", _fail_replace), \
            mock.patch.object(store_mod, "emit_schedule_remove") as emit:
        with pytest.raises(OSError):
            s.remove(job.id)
        with pytest.raises(OSError):
            s.remove_by_name(job.name)
        emit.assert_not_called()
    assert s.get(job.id) is not None
