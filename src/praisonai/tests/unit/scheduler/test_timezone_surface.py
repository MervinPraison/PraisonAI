"""Wrapper CLI/YAML timezone wiring."""

from datetime import datetime, timezone


def _epoch(year, month, day, hour, minute=0):
    return datetime(
        year, month, day, hour, minute, tzinfo=timezone.utc
    ).timestamp()


def test_schedule_ticker_uses_timezone_across_dst():
    from praisonai.scheduler.shared import ScheduleTicker

    ticker = ScheduleTicker(
        "cron:0 8 * * *",
        last_run_at=_epoch(2026, 3, 7, 13),
        timezone="America/New_York",
    )

    assert ticker.is_due(_epoch(2026, 3, 8, 11, 59)) is False
    assert ticker.is_due(_epoch(2026, 3, 8, 12, 0)) is True


def test_yaml_cron_and_timezone_are_preserved(tmp_path):
    from praisonai.scheduler.yaml_loader import load_agent_yaml_with_schedule

    config = tmp_path / "agents.yaml"
    config.write_text(
        "agents:\n"
        "  - name: reporter\n"
        "    instructions: report\n"
        "task: send report\n"
        "schedule:\n"
        "  cron: '0 8 * * *'\n"
        "  tz: America/New_York\n",
        encoding="utf-8",
    )

    _, schedule = load_agent_yaml_with_schedule(str(config))

    assert schedule["interval"] == "cron:0 8 * * *"
    assert schedule["tz"] == "America/New_York"


def test_schedule_add_cli_passes_timezone(monkeypatch):
    from typer.testing import CliRunner

    import praisonaiagents.tools.schedule_tools as tools
    from praisonai.cli.commands.schedule import app

    captured = {}

    def fake_add(**kwargs):
        captured.update(kwargs)
        return "Schedule added"

    monkeypatch.setattr(tools, "schedule_add", fake_add)
    result = CliRunner().invoke(
        app,
        [
            "add",
            "morning-brief",
            "--schedule",
            "cron:0 8 * * *",
            "--tz",
            "America/New_York",
        ],
    )

    assert result.exit_code == 0, result.stdout
    assert captured["tz"] == "America/New_York"


def test_validate_schedule_config_accepts_cron():
    import pytest

    from praisonai.scheduler.yaml_loader import validate_schedule_config

    validate_schedule_config({"interval": "cron:0 8 * * *"})

    with pytest.raises(ValueError, match="empty"):
        validate_schedule_config({"interval": "cron:"})


def test_schedule_ticker_rejects_invalid_timezone():
    import pytest

    from praisonai.scheduler.shared import ScheduleTicker

    with pytest.raises(ValueError, match="Unknown IANA timezone"):
        ScheduleTicker("cron:0 8 * * *", timezone="Mars/Base")
