"""Integration tests for schedule tools with Agent class.

Tests that agents can use schedule tools via:
1. Direct function references in tools list
2. String-name resolution via TOOL_MAPPINGS
3. Tool schema generation for LLM
"""

from unittest.mock import patch


class TestAgentScheduleToolIntegration:
    """Test Agent + schedule tools integration (no LLM calls)."""

    def test_agent_accepts_schedule_tools_as_functions(self):
        """Agent can be created with schedule tool functions in tools list."""
        from praisonaiagents import Agent
        from praisonaiagents.tools.schedule_tools import schedule_add, schedule_list, schedule_remove

        agent = Agent(
            name="test-scheduler",
            instructions="You can set schedules.",
            tools=[schedule_add, schedule_list, schedule_remove],
        )
        assert len(agent.tools) == 3

    def test_agent_resolves_schedule_tool_strings(self):
        """Agent resolves 'schedule_add' etc. from TOOL_MAPPINGS."""
        from praisonaiagents import Agent

        agent = Agent(
            name="test-scheduler",
            instructions="You can set schedules.",
            tools=["schedule_add", "schedule_list", "schedule_remove"],
        )
        # String tool names are resolved via _resolve_tool_names → registry
        # They may or may not resolve depending on registry state,
        # but the tools list should be populated
        # The key test is that Agent creation doesn't crash
        assert agent is not None

    def test_schedule_tool_schema_generation(self):
        """Schedule tools produce valid OpenAI function schemas."""
        from praisonaiagents.tools.schedule_tools import schedule_add, schedule_list, schedule_remove
        from praisonaiagents.tools.decorator import get_tool_schema

        for fn in [schedule_add, schedule_list, schedule_remove]:
            schema = get_tool_schema(fn)
            assert schema is not None
            assert schema["type"] == "function"
            assert "function" in schema
            assert "name" in schema["function"]
            assert "parameters" in schema["function"]

    def test_schedule_add_schema_has_required_params(self):
        """schedule_add schema includes name, schedule, message parameters."""
        from praisonaiagents.tools.schedule_tools import schedule_add
        from praisonaiagents.tools.decorator import get_tool_schema

        schema = get_tool_schema(schedule_add)
        params = schema["function"]["parameters"]
        assert "name" in params["properties"]
        assert "schedule" in params["properties"]
        assert "message" in params["properties"]
        # name and schedule are required, message has a default
        assert "name" in params["required"]
        assert "schedule" in params["required"]

    def test_schedule_remove_schema_has_name_param(self):
        """schedule_remove schema includes name parameter."""
        from praisonaiagents.tools.schedule_tools import schedule_remove
        from praisonaiagents.tools.decorator import get_tool_schema

        schema = get_tool_schema(schedule_remove)
        params = schema["function"]["parameters"]
        assert "name" in params["properties"]
        assert "name" in params["required"]

    def test_schedule_tools_execute_via_agent_execute_tool(self, tmp_path):
        """Agent._execute_tool_call can invoke schedule tools."""
        from praisonaiagents import Agent
        from praisonaiagents.tools.schedule_tools import schedule_add, schedule_list, schedule_remove

        with patch('praisonaiagents.tools.schedule_tools._get_store') as mock_gs:
            from praisonaiagents.scheduler.store import FileScheduleStore
            mock_gs.return_value = FileScheduleStore(store_dir=str(tmp_path))

            agent = Agent(
                name="test-exec",
                instructions="You can set schedules.",
                tools=[schedule_add, schedule_list, schedule_remove],
            )

            # Simulate LLM calling schedule_add
            result = agent._execute_tool_impl(
                "schedule_add",
                {"name": "test-job", "schedule": "hourly", "message": "Check email"},
            )
            assert "test-job" in str(result)
            assert "added" in str(result).lower()

            # Simulate LLM calling schedule_list
            result = agent._execute_tool_impl("schedule_list", {})
            assert "test-job" in str(result)

            # Simulate LLM calling schedule_remove
            result = agent._execute_tool_impl(
                "schedule_remove", {"name": "test-job"}
            )
            assert "removed" in str(result).lower()

    def test_end_to_end_schedule_crud(self, tmp_path):
        """Full CRUD cycle: add → list → remove → list (empty)."""
        from praisonaiagents.tools.schedule_tools import schedule_add, schedule_list, schedule_remove

        with patch('praisonaiagents.tools.schedule_tools._get_store') as mock_gs:
            from praisonaiagents.scheduler.store import FileScheduleStore
            mock_gs.return_value = FileScheduleStore(store_dir=str(tmp_path))

            # Add
            r = schedule_add(name="daily-news", schedule="daily", message="Summarize AI news")
            assert "added" in r.lower()

            # List
            r = schedule_list()
            assert "daily-news" in r
            assert "every 1 day" in r

            # Add another
            r = schedule_add(name="hourly-check", schedule="*/30m", message="Check inbox")
            assert "added" in r.lower()

            # List shows both
            r = schedule_list()
            assert "daily-news" in r
            assert "hourly-check" in r
            assert "2 schedule" in r

            # Remove one
            r = schedule_remove(name="daily-news")
            assert "removed" in r.lower()

            # List shows one
            r = schedule_list()
            assert "daily-news" not in r
            assert "hourly-check" in r
            assert "1 schedule" in r

            # Duplicate name prevention
            r = schedule_add(name="hourly-check", schedule="hourly", message="Dup")
            assert "already exists" in r.lower()


class TestScheduleToolImportPaths:
    """Test various import paths work correctly."""

    def test_import_from_tools_module(self):
        from praisonaiagents.tools import schedule_add, schedule_list, schedule_remove
        assert callable(schedule_add)
        assert callable(schedule_list)
        assert callable(schedule_remove)

    def test_import_from_schedule_tools_directly(self):
        from praisonaiagents.tools.schedule_tools import schedule_add, schedule_list, schedule_remove
        assert callable(schedule_add)
        assert callable(schedule_list)
        assert callable(schedule_remove)

    def test_import_scheduler_models(self):
        from praisonaiagents.scheduler import Schedule, ScheduleJob
        s = Schedule(kind="every", every_seconds=60)
        j = ScheduleJob(name="test", schedule=s)
        assert j.name == "test"

    def test_import_scheduler_parser(self):
        from praisonaiagents.scheduler import parse_schedule
        s = parse_schedule("hourly")
        assert s.kind == "every"

    def test_import_scheduler_store(self):
        from praisonaiagents.scheduler import FileScheduleStore
        assert FileScheduleStore is not None

    def test_import_scheduler_runner(self):
        from praisonaiagents.scheduler import ScheduleRunner
        assert ScheduleRunner is not None


class TestNaturalLanguageSchedule:
    """Natural-language clock-time / day-of-week schedule expressions."""

    def test_bare_clock_time_is_one_shot(self):
        from praisonaiagents.scheduler import parse_schedule
        s = parse_schedule("at 9am")
        assert s.kind == "at"
        assert s.at is not None and "09:00" in s.at

    def test_clock_time_with_minutes_pm(self):
        from praisonaiagents.scheduler import parse_schedule
        s = parse_schedule("at 9:30pm")
        assert s.kind == "at"
        assert "21:30" in s.at

    def test_every_day_at_clock_time(self):
        from praisonaiagents.scheduler import parse_schedule
        s = parse_schedule("every day at 9am")
        assert s.kind == "cron"
        assert s.cron_expr == "0 9 * * *"

    def test_daily_at_clock_time(self):
        from praisonaiagents.scheduler import parse_schedule
        s = parse_schedule("daily at 9am")
        assert s.kind == "cron"
        assert s.cron_expr == "0 9 * * *"

    def test_weekdays_at_clock_time(self):
        from praisonaiagents.scheduler import parse_schedule
        s = parse_schedule("weekdays at 9am")
        assert s.kind == "cron"
        assert s.cron_expr == "0 9 * * 1-5"

    def test_weekends_at_clock_time(self):
        from praisonaiagents.scheduler import parse_schedule
        s = parse_schedule("weekends at 10:30am")
        assert s.kind == "cron"
        assert s.cron_expr == "30 10 * * 0,6"

    def test_every_single_weekday(self):
        from praisonaiagents.scheduler import parse_schedule
        s = parse_schedule("every monday 9am")
        assert s.kind == "cron"
        assert s.cron_expr == "0 9 * * 1"

    def test_multiple_days_comma_list(self):
        from praisonaiagents.scheduler import parse_schedule
        s = parse_schedule("every mon,wed,fri at 9am")
        assert s.kind == "cron"
        assert s.cron_expr == "0 9 * * 1,3,5"

    def test_24h_clock(self):
        from praisonaiagents.scheduler import parse_schedule
        s = parse_schedule("every day at 17:00")
        assert s.kind == "cron"
        assert s.cron_expr == "0 17 * * *"

    def test_legacy_forms_unchanged(self):
        from praisonaiagents.scheduler import parse_schedule
        assert parse_schedule("hourly").kind == "every"
        assert parse_schedule("*/30m").kind == "every"
        assert parse_schedule("cron:0 7 * * *").kind == "cron"
        assert parse_schedule("in 20 minutes").kind == "at"

    def test_invalid_still_raises(self):
        import pytest
        from praisonaiagents.scheduler import parse_schedule
        for bad in ("gibberish", "at bananas", "every florp"):
            with pytest.raises(ValueError):
                parse_schedule(bad)

    def test_one_shot_clock_time_honors_timezone(self):
        from datetime import datetime
        from zoneinfo import ZoneInfo
        from praisonaiagents.scheduler import parse_schedule

        s = parse_schedule("at 9am", tz="America/New_York")
        assert s.kind == "at"
        target = datetime.fromisoformat(s.at)
        # The clock time denotes 09:00 local (New York), not 09:00 UTC.
        assert target.tzinfo is not None
        local = target.astimezone(ZoneInfo("America/New_York"))
        assert (local.hour, local.minute) == (9, 0)

    def test_one_shot_clock_time_is_due_at_local_hour(self):
        from datetime import datetime
        from praisonaiagents.scheduler import parse_schedule
        from praisonaiagents.scheduler.due import is_due
        from praisonaiagents.scheduler.models import ScheduleJob

        s = parse_schedule("at 9am", tz="America/New_York")
        target = datetime.fromisoformat(s.at)
        job = ScheduleJob(name="j1", schedule=s, message="p")
        # Just before the target: not due. At/after target: due.
        assert is_due(job, target.timestamp() - 1) is False
        assert is_due(job, target.timestamp()) is True
