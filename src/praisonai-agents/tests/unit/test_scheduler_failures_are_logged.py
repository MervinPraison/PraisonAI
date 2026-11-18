"""Failures swallowed in ``praisonaiagents/scheduler/`` leave a debug trace (T-08).

The four blocks were the file-lock release in the two schedule stores. A
release failure is harmless (closing the lock file releases it), so behaviour
is unchanged -- the job is still saved -- but a debug record now says so.
"""

import ast
import logging
import sys
import types
from pathlib import Path

import pytest

import praisonaiagents.scheduler as scheduler_pkg
from praisonaiagents.scheduler import config_store as config_store_mod
from praisonaiagents.scheduler import store as store_mod
from praisonaiagents.scheduler.models import Schedule, ScheduleJob

SCHEDULER_DIR = Path(scheduler_pkg.__file__).parent

# (file, function) pairs deliberately left as broad silent handlers. None.
KEPT_SILENT = set()


def _silent_broad_handlers():
    found = set()
    for path in sorted(SCHEDULER_DIR.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for func in ast.walk(tree):
            if not isinstance(func, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for node in ast.walk(func):
                if not (isinstance(node, ast.ExceptHandler) and len(node.body) == 1
                        and isinstance(node.body[0], ast.Pass)):
                    continue
                t = node.type
                names = ([t.id] if isinstance(t, ast.Name)
                         else [e.id for e in t.elts if isinstance(e, ast.Name)]
                         if isinstance(t, ast.Tuple) else [])
                if t is None or {"Exception", "BaseException"} & set(names):
                    found.add((path.relative_to(SCHEDULER_DIR).as_posix(), func.name))
    return found


def _job(name="nightly"):
    return ScheduleJob(name=name, schedule=Schedule(kind="every", every_seconds=60),
                       message="hello")


def _debug_records_with_traceback(caplog, logger_name):
    return [r for r in caplog.records
            if r.name == logger_name and r.levelno == logging.DEBUG and r.exc_info]


def test_only_deliberate_silent_handlers_remain():
    assert _silent_broad_handlers() == KEPT_SILENT


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX fcntl path")
def test_posix_unlock_failure_is_logged_and_job_still_saved(tmp_path, monkeypatch, caplog):
    import fcntl

    real_flock = fcntl.flock

    def flock(fd, op):
        if op == fcntl.LOCK_UN:
            raise OSError("unlock failed")
        return real_flock(fd, op)

    monkeypatch.setattr(fcntl, "flock", flock)
    store = store_mod.FileScheduleStore(store_dir=str(tmp_path))
    with caplog.at_level(logging.DEBUG, logger=store_mod.logger.name):
        store.add(_job())

    monkeypatch.setattr(fcntl, "flock", real_flock)
    reread = store_mod.FileScheduleStore(store_dir=str(tmp_path))
    assert [j.name for j in reread.list()] == ["nightly"]
    records = _debug_records_with_traceback(caplog, store_mod.logger.name)
    assert records and "lock" in records[0].getMessage()


def test_windows_unlock_failure_is_logged_and_job_still_saved(tmp_path, monkeypatch, caplog):
    """Drive the msvcrt branch with a fake module: lock works, unlock raises."""
    fake = types.ModuleType("msvcrt")
    fake.LK_LOCK, fake.LK_UNLCK = 1, 0

    def locking(fd, mode, nbytes):
        if mode == fake.LK_UNLCK:
            raise OSError("unlock failed")

    fake.locking = locking
    monkeypatch.setitem(sys.modules, "fcntl", None)  # `import fcntl` -> ImportError
    monkeypatch.setitem(sys.modules, "msvcrt", fake)

    path = tmp_path / "config.yaml"
    store = config_store_mod.ConfigYamlScheduleStore(config_path=str(path))
    with caplog.at_level(logging.DEBUG, logger=config_store_mod.logger.name):
        store.add(_job())

    monkeypatch.undo()
    reread = config_store_mod.ConfigYamlScheduleStore(config_path=str(path))
    assert [j.name for j in reread.list()] == ["nightly"]
    records = _debug_records_with_traceback(caplog, config_store_mod.logger.name)
    assert records and "Windows file lock" in records[0].getMessage()
