"""Cron schedules must actually fire, and must be refused when they cannot.

``croniter`` was declared in none of the nine pyproject.toml files, so on a
default install every cron-kind schedule -- and every natural-language
recurring one, since "every day at 9am" is converted to cron -- was accepted,
persisted, and returned False from is_due() forever. No error at creation; a
warning in a log nobody reads; a job that never runs.

Three guards, one per layer of the failure:
  * the dependency is declared, so a fresh install has the engine;
  * a cron job genuinely becomes due, proving the runtime path end to end;
  * creation refuses a cron schedule when the engine is absent, so the
    failure is loud at the one moment the user can act on it.
"""
import pathlib
import sys

import pytest

from praisonaiagents.scheduler.due import is_due
from praisonaiagents.scheduler.models import ScheduleJob
from praisonaiagents.scheduler.parser import parse_schedule

_PYPROJECT = pathlib.Path(__file__).resolve().parents[2] / "pyproject.toml"
EIGHT_DAYS = 8 * 86400   # covers daily AND weekly ("every monday") schedules


def _job(expr: str) -> ScheduleJob:
    return ScheduleJob(name="t", schedule=parse_schedule(expr), message="hi")


def test_cron_engine_is_a_declared_dependency():
    """Packaging, not code, was the defect; pin the packaging."""
    text = _PYPROJECT.read_text()
    deps = text[text.index("dependencies = ["):]
    deps = deps[: deps.index("]")]
    assert "croniter" in deps, "croniter missing from core dependencies"


@pytest.mark.parametrize("expr", [
    "every day at 9am",
    "weekdays at 9am",
    "every monday 9am",
    "cron:0 9 * * *",
])
def test_recurring_schedule_actually_becomes_due(expr):
    """The effect: eight days after creation, daily and weekly jobs are due."""
    job = _job(expr)
    assert job.schedule.kind == "cron", "these must route through cron"
    assert is_due(job, job.created_at + EIGHT_DAYS), (
        f"{expr!r} was accepted but never becomes due"
    )


def test_interval_and_one_shot_do_not_need_the_engine(monkeypatch):
    """Do not over-restrict: 'hourly' and 'in 20 minutes' never used cron."""
    monkeypatch.setitem(sys.modules, "croniter", None)
    for expr in ("hourly", "*/30m", "in 20 minutes"):
        job = _job(expr)
        assert is_due(job, job.created_at + EIGHT_DAYS)


def test_cron_schedule_is_refused_when_the_engine_is_missing(monkeypatch):
    """Loud at creation. Setting the module to None makes import raise."""
    monkeypatch.setitem(sys.modules, "croniter", None)
    with pytest.raises(ValueError, match="cron engine"):
        parse_schedule("every day at 9am")
    with pytest.raises(ValueError, match="cron engine"):
        parse_schedule("cron:0 9 * * *")
