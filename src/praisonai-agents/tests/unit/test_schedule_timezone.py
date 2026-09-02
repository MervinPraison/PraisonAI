"""Timezone and DST coverage for the core scheduler."""

import os
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from praisonaiagents.scheduler.due import is_due, next_fire_time
from praisonaiagents.scheduler.models import Schedule


def _epoch(year, month, day, hour, minute=0):
    return datetime(
        year, month, day, hour, minute, tzinfo=timezone.utc
    ).timestamp()


def _job(schedule, *, created_at=0.0, last_run_at=None):
    return SimpleNamespace(
        id="timezone-test",
        schedule=schedule,
        created_at=created_at,
        last_run_at=last_run_at,
    )


def test_cron_keeps_local_hour_across_spring_dst_transition():
    pytest.importorskip("croniter")
    next_run = next_fire_time(
        "0 8 * * *",
        _epoch(2026, 3, 7, 13),
        "America/New_York",
    )

    assert next_run == _epoch(2026, 3, 8, 12)


def test_cron_keeps_local_hour_across_fall_dst_transition():
    pytest.importorskip("croniter")
    next_run = next_fire_time(
        "0 8 * * *",
        _epoch(2026, 10, 31, 12),
        "America/New_York",
    )

    assert next_run == _epoch(2026, 11, 1, 13)


def test_naive_one_shot_uses_schedule_timezone():
    job = _job(Schedule(
        kind="at",
        at="2026-07-01T09:00:00",
        tz="America/New_York",
    ))

    assert is_due(job, _epoch(2026, 7, 1, 12, 59)) is False
    assert is_due(job, _epoch(2026, 7, 1, 13, 0)) is True


def test_offset_one_shot_keeps_its_explicit_offset():
    job = _job(Schedule(
        kind="at",
        at="2026-07-01T09:00:00+02:00",
        tz="America/New_York",
    ))

    assert is_due(job, _epoch(2026, 7, 1, 7, 0)) is True


def test_naive_one_shot_local_fallback_honours_target_date_dst():
    import time as _time

    if not hasattr(_time, "tzset"):
        pytest.skip("time.tzset unavailable on this platform")

    original_tz = os.environ.get("TZ")
    os.environ["TZ"] = "Europe/London"
    _time.tzset()
    try:
        # Target sits in GMT (winter, +00:00) even though the check runs while
        # the fixture below evaluates "now"; the naive wall clock must resolve
        # against the target date's offset, not a fixed current-day offset.
        job = _job(Schedule(kind="at", at="2027-01-15T12:00:00"))

        assert is_due(job, _epoch(2027, 1, 15, 11, 59)) is False
        assert is_due(job, _epoch(2027, 1, 15, 12, 0)) is True
    finally:
        if original_tz is None:
            os.environ.pop("TZ", None)
        else:
            os.environ["TZ"] = original_tz
        _time.tzset()


def test_instance_timezone_environment_is_default(monkeypatch):
    monkeypatch.setenv("PRAISONAI_SCHEDULE_TIMEZONE", "Asia/Singapore")
    job = _job(Schedule(kind="at", at="2026-07-01T09:00:00"))

    assert is_due(job, _epoch(2026, 7, 1, 0, 59)) is False
    assert is_due(job, _epoch(2026, 7, 1, 1, 0)) is True


def test_invalid_timezone_fails_closed(caplog):
    job = _job(Schedule(kind="at", at="2026-07-01T09:00:00", tz="Mars/Base"))

    assert is_due(job, _epoch(2026, 7, 1, 9, 0)) is False
    assert "Invalid 'at' timestamp" in caplog.text


def test_parser_sets_and_validates_timezone():
    from praisonaiagents.scheduler.parser import parse_schedule

    schedule = parse_schedule("cron:0 8 * * *", tz="America/New_York")
    assert schedule.tz == "America/New_York"
    with pytest.raises(ValueError, match="Unknown IANA timezone"):
        parse_schedule("daily", tz="Mars/Base")


def test_schedule_tool_persists_timezone(tmp_path):
    from unittest.mock import patch

    from praisonaiagents.scheduler.store import FileScheduleStore
    from praisonaiagents.tools.schedule_tools import schedule_add

    store = FileScheduleStore(store_dir=str(tmp_path))
    with patch(
        "praisonaiagents.tools.schedule_tools._get_store",
        return_value=store,
    ):
        result = schedule_add(
            name="morning-brief",
            schedule="cron:0 8 * * *",
            tz="America/New_York",
        )

    assert "tz=America/New_York" in result
    assert store.get_by_name("morning-brief").schedule.tz == "America/New_York"


def test_config_store_uses_instance_default_timezone(tmp_path):
    import yaml

    from praisonaiagents.scheduler.config_store import ConfigYamlScheduleStore
    from praisonaiagents.scheduler.models import ScheduleJob

    job = ScheduleJob(
        id="brief",
        name="brief",
        schedule=Schedule(kind="at", at="2026-07-01T09:00:00"),
    )
    config = tmp_path / "config.yaml"
    config.write_text(
        yaml.safe_dump({
            "scheduler": {"timezone": "America/New_York"},
            "schedules": {job.id: job.to_dict()},
        }),
        encoding="utf-8",
    )
    store = ConfigYamlScheduleStore(str(config))

    assert store.claim_due(_epoch(2026, 7, 1, 12, 59), "worker") == []
    claimed = store.claim_due(_epoch(2026, 7, 1, 13, 0), "worker")
    assert [item.id for item in claimed] == ["brief"]


def test_config_store_rejects_invalid_instance_timezone(tmp_path):
    import yaml

    from praisonaiagents.scheduler.config_store import ConfigYamlScheduleStore

    config = tmp_path / "config.yaml"
    config.write_text(
        yaml.safe_dump({"scheduler": {"timezone": "Mars/Base"}}),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Mars/Base"):
        ConfigYamlScheduleStore(str(config))


def _schedule_agent_fixture(tmp_path):
    from praisonaiagents.scheduler.store import FileScheduleStore
    from praisonaiagents.tools.schedule_tools import schedule_add

    return FileScheduleStore(store_dir=str(tmp_path)), schedule_add


def test_schedule_tool_agent_smoke(monkeypatch, tmp_path):
    from unittest.mock import patch

    from praisonaiagents import Agent

    store, schedule_add = _schedule_agent_fixture(tmp_path)
    agent = Agent(
        name="schedule-smoke",
        instructions="Use the scheduling tool to create the requested job.",
        tools=[schedule_add],
    )
    monkeypatch.setattr(
        agent,
        "chat",
        lambda prompt, **kwargs: schedule_add(
            name="agent-morning-brief",
            schedule="cron:0 8 * * *",
            tz="America/New_York",
        ),
    )

    with patch(
        "praisonaiagents.tools.schedule_tools._get_store", return_value=store
    ):
        result = agent.start("Schedule a morning brief for 8 AM New York time.")
    print(result)

    assert store.get_by_name("agent-morning-brief").schedule.tz == "America/New_York"


@pytest.mark.network
@pytest.mark.skipif(
    os.environ.get("RUN_REAL_KEY_TESTS") != "1"
    or not os.environ.get("OPENAI_API_KEY"),
    reason="Set RUN_REAL_KEY_TESTS=1 and OPENAI_API_KEY for the real agentic test",
)
def test_schedule_tool_real_agentic(tmp_path):
    from unittest.mock import patch

    from praisonaiagents import Agent

    store, schedule_add = _schedule_agent_fixture(tmp_path)
    agent = Agent(
        name="schedule-agentic",
        model="gpt-4o-mini",
        instructions=(
            "Always use schedule_add for scheduling requests and preserve the "
            "timezone exactly as requested."
        ),
        tools=[schedule_add],
    )

    with patch(
        "praisonaiagents.tools.schedule_tools._get_store", return_value=store
    ):
        result = agent.start(
            "Use schedule_add to create a job named agent-morning-brief at "
            "cron:0 8 * * * with timezone America/New_York."
        )
    print(result)

    assert result
    assert store.get_by_name("agent-morning-brief").schedule.tz == "America/New_York"
