"""Naive one-shot ``at`` timestamps mean the user's wall clock, not UTC.

Regression for #4691: ``parse_schedule`` used to store ``at:<naive iso>``
verbatim and ``_clock_to_next_at`` computed ``at 9am`` in UTC, so a person
in London typing a local time got a job that fired an hour off. The parser
now stamps every ``at`` it produces with the zone the person meant -- the
schedule ``tz``, else ``PRAISONAI_SCHEDULE_TIMEZONE``, else the system's
local zone -- so the stored value is an unambiguous instant and ``is_due()``
never has to guess.

The system zone is forced with ``TZ`` + ``time.tzset`` so these tests mean
the same thing on a UTC CI runner as on a developer's laptop. Europe/London
is the zone from the issue, UTC the control, and Asia/Kolkata (+05:30, no
DST) the zone that keeps the assertions distinguishable from UTC in winter.
"""

import os
import time
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from praisonaiagents.scheduler.due import is_due
from praisonaiagents.scheduler.models import Schedule, ScheduleJob
from praisonaiagents.scheduler.parser import parse_schedule

pytestmark = pytest.mark.skipif(
    not hasattr(time, "tzset"), reason="time.tzset() is POSIX-only"
)


@pytest.fixture
def system_tz(monkeypatch):
    """Force the process-local zone; unset the scheduler's env default."""
    monkeypatch.delenv("PRAISONAI_SCHEDULE_TIMEZONE", raising=False)
    previous = os.environ.get("TZ")

    def _set(name: str) -> None:
        os.environ["TZ"] = name
        time.tzset()

    yield _set

    if previous is None:
        os.environ.pop("TZ", None)
    else:
        os.environ["TZ"] = previous
    time.tzset()


def _utc(year, month, day, hour, minute=0):
    return datetime(year, month, day, hour, minute, tzinfo=timezone.utc)


def _job(schedule):
    return ScheduleJob(name="wall-clock", schedule=schedule, message="x")


@pytest.mark.parametrize("zone", ["Europe/London", "UTC", "Asia/Kolkata"])
def test_naive_at_iso_is_due_at_the_local_wall_clock_time(system_tz, zone):
    """The scenario from the issue: type a local time one minute ahead."""
    system_tz(zone)
    local = (datetime.now() + timedelta(minutes=1)).replace(microsecond=0)

    job = _job(parse_schedule(f"at:{local.isoformat()}"))

    # ``local.timestamp()`` is the instant that wall-clock reading denotes
    # in the forced system zone. Due one second after it, not one before.
    assert is_due(job, now=local.timestamp() + 1) is True
    assert is_due(job, now=local.timestamp() - 1) is False


@pytest.mark.parametrize("zone", ["Europe/London", "UTC", "Asia/Kolkata"])
def test_naive_at_iso_is_stored_aware_in_the_local_zone(system_tz, zone):
    """The stored string names an instant; nothing downstream has to guess."""
    system_tz(zone)
    local = (datetime.now() + timedelta(minutes=1)).replace(microsecond=0)

    stored = datetime.fromisoformat(parse_schedule(f"at:{local.isoformat()}").at)

    assert stored.tzinfo is not None
    assert stored.replace(tzinfo=None) == local  # wall-clock reading kept
    assert stored.timestamp() == local.timestamp()  # ...in the local zone


def test_naive_at_iso_uses_the_offset_in_force_on_that_date(system_tz):
    """London is +01:00 in summer and +00:00 in winter; each date gets its own."""
    system_tz("Europe/London")

    summer = datetime.fromisoformat(parse_schedule("at:2026-07-01T09:00:00").at)
    winter = datetime.fromisoformat(parse_schedule("at:2026-12-01T09:00:00").at)

    assert summer == _utc(2026, 7, 1, 8)
    assert winter == _utc(2026, 12, 1, 9)


def test_explicit_schedule_tz_beats_the_system_zone(system_tz):
    system_tz("Europe/London")

    stored = datetime.fromisoformat(
        parse_schedule("at:2026-07-01T09:00:00", tz="America/New_York").at
    )

    assert stored == _utc(2026, 7, 1, 13)


def test_env_default_beats_the_system_zone(system_tz, monkeypatch):
    system_tz("Europe/London")
    monkeypatch.setenv("PRAISONAI_SCHEDULE_TIMEZONE", "Asia/Singapore")

    stored = datetime.fromisoformat(parse_schedule("at:2026-07-01T09:00:00").at)

    assert stored == _utc(2026, 7, 1, 1)


def test_explicit_offset_in_the_string_is_kept_verbatim(system_tz):
    system_tz("Europe/London")

    s = parse_schedule("at:2026-07-01T09:00:00+02:00", tz="America/New_York")

    assert s.at == "2026-07-01T09:00:00+02:00"
    assert datetime.fromisoformat(s.at) == _utc(2026, 7, 1, 7)


# Asia/Kolkata is +05:30 all year: London coincides with UTC in winter, so a
# UTC-stamping regression would go unnoticed there for half the year.
@pytest.mark.parametrize("zone", ["Europe/London", "Asia/Kolkata"])
def test_bare_clock_time_means_the_local_wall_clock(system_tz, zone):
    """``at 9am`` typed in London is 09:00 London, not 09:00 UTC."""
    system_tz(zone)

    stored = datetime.fromisoformat(parse_schedule("at 9am").at)

    assert stored.tzinfo is not None
    local = stored.astimezone(ZoneInfo(zone))
    assert (local.hour, local.minute) == (9, 0)
    # And it is the *next* 09:00 in that zone, within the coming day.
    now = datetime.now(ZoneInfo(zone))
    assert now < stored <= now + timedelta(days=1)


def test_legacy_naive_stored_string_is_read_as_the_local_wall_clock(system_tz):
    """A job stored before zones were stamped is still read as local time.

    Documents the fallback ``is_due()`` applies to a naive string that did
    not come through the parser (an old job file, a hand-written
    config.yaml): the schedule tz, else the instance default, else
    PRAISONAI_SCHEDULE_TIMEZONE, else the runner's local zone -- with the
    offset in force on that date.
    """
    system_tz("Europe/London")
    summer = _job(Schedule(kind="at", at="2026-07-01T09:00:00"))
    winter = _job(Schedule(kind="at", at="2026-12-01T09:00:00"))

    assert is_due(summer, _utc(2026, 7, 1, 7, 59).timestamp()) is False
    assert is_due(summer, _utc(2026, 7, 1, 8).timestamp()) is True
    assert is_due(winter, _utc(2026, 12, 1, 8, 59).timestamp()) is False
    assert is_due(winter, _utc(2026, 12, 1, 9).timestamp()) is True
