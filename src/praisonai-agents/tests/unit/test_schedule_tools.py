"""TDD tests for schedule tools — agent-centric scheduling via tools.

Tests cover:
1. Schedule models (ScheduleJob, Schedule)
2. FileScheduleStore (CRUD + persistence)
3. Schedule tools (schedule_add, schedule_list, schedule_remove)
4. Schedule parser (interval, cron, at)
5. ScheduleRunner (tick loop)
6. Integration: agent uses schedule tools
"""

import time
import pytest
from unittest.mock import patch


# ─── 1. Model Tests ──────────────────────────────────────────────────────────

class TestScheduleModels:
    """Test ScheduleJob and Schedule dataclasses."""

    def test_schedule_every_creation(self):
        from praisonaiagents.scheduler.models import Schedule
        s = Schedule(kind="every", every_seconds=3600)
        assert s.kind == "every"
        assert s.every_seconds == 3600

    def test_schedule_cron_creation(self):
        from praisonaiagents.scheduler.models import Schedule
        s = Schedule(kind="cron", cron_expr="0 7 * * *")
        assert s.kind == "cron"
        assert s.cron_expr == "0 7 * * *"

    def test_schedule_at_creation(self):
        from praisonaiagents.scheduler.models import Schedule
        s = Schedule(kind="at", at="2026-03-01T09:00:00")
        assert s.kind == "at"
        assert s.at == "2026-03-01T09:00:00"

    def test_schedule_job_creation(self):
        from praisonaiagents.scheduler.models import ScheduleJob, Schedule
        sched = Schedule(kind="every", every_seconds=60)
        job = ScheduleJob(
            name="test-job",
            schedule=sched,
            message="Hello world",
        )
        assert job.name == "test-job"
        assert job.id  # auto-generated
        assert job.enabled is True
        assert job.message == "Hello world"

    def test_schedule_job_to_dict_roundtrip(self):
        from praisonaiagents.scheduler.models import ScheduleJob, Schedule
        sched = Schedule(kind="every", every_seconds=300)
        job = ScheduleJob(name="roundtrip", schedule=sched, message="test")
        d = job.to_dict()
        assert isinstance(d, dict)
        assert d["name"] == "roundtrip"
        assert d["schedule"]["kind"] == "every"
        # Roundtrip
        job2 = ScheduleJob.from_dict(d)
        assert job2.name == job.name
        assert job2.id == job.id
        assert job2.schedule.every_seconds == 300

    def test_schedule_job_defaults(self):
        from praisonaiagents.scheduler.models import ScheduleJob, Schedule
        sched = Schedule(kind="every", every_seconds=60)
        job = ScheduleJob(name="defaults", schedule=sched)
        assert job.enabled is True
        assert job.message == ""
        assert job.agent_id is None
        assert job.session_target == "isolated"
        assert job.delete_after_run is False


# ─── 2. Store Tests ──────────────────────────────────────────────────────────

class TestFileScheduleStore:
    """Test FileScheduleStore CRUD and persistence."""

    def _make_store(self, tmp_path):
        from praisonaiagents.scheduler.store import FileScheduleStore
        return FileScheduleStore(store_dir=str(tmp_path))

    def _make_job(self, name="test-job"):
        from praisonaiagents.scheduler.models import ScheduleJob, Schedule
        return ScheduleJob(
            name=name,
            schedule=Schedule(kind="every", every_seconds=60),
            message="test message",
        )

    def test_add_and_get(self, tmp_path):
        store = self._make_store(tmp_path)
        job = self._make_job()
        store.add(job)
        retrieved = store.get(job.id)
        assert retrieved is not None
        assert retrieved.name == "test-job"

    def test_add_duplicate_id_raises(self, tmp_path):
        store = self._make_store(tmp_path)
        job = self._make_job()
        store.add(job)
        with pytest.raises(ValueError, match="already exists"):
            store.add(job)

    def test_list_all(self, tmp_path):
        store = self._make_store(tmp_path)
        store.add(self._make_job("job-1"))
        store.add(self._make_job("job-2"))
        jobs = store.list()
        assert len(jobs) == 2

    def test_list_by_agent_id(self, tmp_path):
        from praisonaiagents.scheduler.models import ScheduleJob, Schedule
        store = self._make_store(tmp_path)
        j1 = ScheduleJob(name="a", schedule=Schedule(kind="every", every_seconds=60), agent_id="agent-1")
        j2 = ScheduleJob(name="b", schedule=Schedule(kind="every", every_seconds=60), agent_id="agent-2")
        store.add(j1)
        store.add(j2)
        assert len(store.list(agent_id="agent-1")) == 1

    def test_remove(self, tmp_path):
        store = self._make_store(tmp_path)
        job = self._make_job()
        store.add(job)
        assert store.remove(job.id) is True
        assert store.get(job.id) is None

    def test_remove_nonexistent(self, tmp_path):
        store = self._make_store(tmp_path)
        assert store.remove("nonexistent") is False

    def test_persistence_across_instances(self, tmp_path):
        store1 = self._make_store(tmp_path)
        job = self._make_job()
        store1.add(job)

        # New store instance reads from same dir
        store2 = self._make_store(tmp_path)
        retrieved = store2.get(job.id)
        assert retrieved is not None
        assert retrieved.name == "test-job"

    def test_update(self, tmp_path):
        store = self._make_store(tmp_path)
        job = self._make_job()
        store.add(job)
        job.enabled = False
        store.update(job)
        retrieved = store.get(job.id)
        assert retrieved.enabled is False

    def test_empty_store_list(self, tmp_path):
        store = self._make_store(tmp_path)
        assert store.list() == []


# ─── 3. Parser Tests ─────────────────────────────────────────────────────────

class TestScheduleParser:
    """Test schedule expression parsing."""

    def test_parse_hourly(self):
        from praisonaiagents.scheduler.parser import parse_schedule
        s = parse_schedule("hourly")
        assert s.kind == "every"
        assert s.every_seconds == 3600

    def test_parse_daily(self):
        from praisonaiagents.scheduler.parser import parse_schedule
        s = parse_schedule("daily")
        assert s.kind == "every"
        assert s.every_seconds == 86400

    def test_parse_interval_minutes(self):
        from praisonaiagents.scheduler.parser import parse_schedule
        s = parse_schedule("*/30m")
        assert s.kind == "every"
        assert s.every_seconds == 1800

    def test_parse_interval_hours(self):
        from praisonaiagents.scheduler.parser import parse_schedule
        s = parse_schedule("*/6h")
        assert s.kind == "every"
        assert s.every_seconds == 21600

    def test_parse_interval_seconds(self):
        from praisonaiagents.scheduler.parser import parse_schedule
        s = parse_schedule("*/10s")
        assert s.kind == "every"
        assert s.every_seconds == 10

    def test_parse_cron_expression(self):
        from praisonaiagents.scheduler.parser import parse_schedule
        s = parse_schedule("cron:0 7 * * *")
        assert s.kind == "cron"
        assert s.cron_expr == "0 7 * * *"

    def test_parse_at_iso(self):
        from praisonaiagents.scheduler.parser import parse_schedule
        s = parse_schedule("at:2026-03-01T09:00:00")
        assert s.kind == "at"
        assert s.at == "2026-03-01T09:00:00"

    def test_parse_numeric_seconds(self):
        from praisonaiagents.scheduler.parser import parse_schedule
        s = parse_schedule("3600")
        assert s.kind == "every"
        assert s.every_seconds == 3600

    def test_parse_relative_minutes(self):
        from praisonaiagents.scheduler.parser import parse_schedule
        s = parse_schedule("in 20 minutes")
        assert s.kind == "at"
        assert s.at is not None  # Should be an ISO timestamp ~20min from now

    def test_parse_invalid_raises(self):
        from praisonaiagents.scheduler.parser import parse_schedule
        with pytest.raises(ValueError):
            parse_schedule("")


# ─── 4. Schedule Tool Tests ──────────────────────────────────────────────────

class TestScheduleTools:
    """Test schedule_add, schedule_list, schedule_remove tool functions."""

    def test_schedule_add_returns_confirmation(self, tmp_path):
        from praisonaiagents.tools.schedule_tools import schedule_add
        with patch('praisonaiagents.tools.schedule_tools._get_store') as mock_gs:
            from praisonaiagents.scheduler.store import FileScheduleStore
            mock_gs.return_value = FileScheduleStore(store_dir=str(tmp_path))
            result = schedule_add(name="test-reminder", schedule="hourly", message="Check email")
        assert "test-reminder" in result
        assert "scheduled" in result.lower() or "added" in result.lower()

    def test_schedule_list_returns_jobs(self, tmp_path):
        from praisonaiagents.tools.schedule_tools import schedule_list, schedule_add
        with patch('praisonaiagents.tools.schedule_tools._get_store') as mock_gs:
            from praisonaiagents.scheduler.store import FileScheduleStore
            store = FileScheduleStore(store_dir=str(tmp_path))
            mock_gs.return_value = store
            schedule_add(name="job-1", schedule="hourly", message="Task 1")
            schedule_add(name="job-2", schedule="daily", message="Task 2")
            result = schedule_list()
        assert "job-1" in result
        assert "job-2" in result

    def test_schedule_remove_returns_confirmation(self, tmp_path):
        from praisonaiagents.tools.schedule_tools import schedule_add, schedule_remove
        with patch('praisonaiagents.tools.schedule_tools._get_store') as mock_gs:
            from praisonaiagents.scheduler.store import FileScheduleStore
            store = FileScheduleStore(store_dir=str(tmp_path))
            mock_gs.return_value = store
            schedule_add(name="to-remove", schedule="hourly", message="Temp")
            result = schedule_remove(name="to-remove")
        assert "removed" in result.lower() or "deleted" in result.lower()

    def test_schedule_remove_nonexistent(self, tmp_path):
        from praisonaiagents.tools.schedule_tools import schedule_remove
        with patch('praisonaiagents.tools.schedule_tools._get_store') as mock_gs:
            from praisonaiagents.scheduler.store import FileScheduleStore
            mock_gs.return_value = FileScheduleStore(store_dir=str(tmp_path))
            result = schedule_remove(name="nonexistent")
        assert "not found" in result.lower()

    def test_schedule_list_empty(self, tmp_path):
        from praisonaiagents.tools.schedule_tools import schedule_list
        with patch('praisonaiagents.tools.schedule_tools._get_store') as mock_gs:
            from praisonaiagents.scheduler.store import FileScheduleStore
            mock_gs.return_value = FileScheduleStore(store_dir=str(tmp_path))
            result = schedule_list()
        assert "no schedule" in result.lower() or "empty" in result.lower() or "0" in result


# ─── 5. Runner Tests ─────────────────────────────────────────────────────────

class TestScheduleRunner:
    """Test ScheduleRunner tick loop."""

    def test_runner_creation(self, tmp_path):
        from praisonaiagents.scheduler.runner import ScheduleRunner
        from praisonaiagents.scheduler.store import FileScheduleStore
        store = FileScheduleStore(store_dir=str(tmp_path))
        runner = ScheduleRunner(store=store)
        assert runner is not None

    def test_get_due_jobs_interval(self, tmp_path):
        from praisonaiagents.scheduler.runner import ScheduleRunner
        from praisonaiagents.scheduler.store import FileScheduleStore
        from praisonaiagents.scheduler.models import ScheduleJob, Schedule
        store = FileScheduleStore(store_dir=str(tmp_path))
        # Job with 1-second interval, last_run 10 seconds ago
        job = ScheduleJob(
            name="due-job",
            schedule=Schedule(kind="every", every_seconds=1),
            message="test",
        )
        job.last_run_at = time.time() - 10  # Ran 10s ago, interval is 1s → due
        store.add(job)
        runner = ScheduleRunner(store=store)
        due = runner.get_due_jobs()
        assert len(due) == 1
        assert due[0].name == "due-job"

    def test_get_due_jobs_not_yet(self, tmp_path):
        from praisonaiagents.scheduler.runner import ScheduleRunner
        from praisonaiagents.scheduler.store import FileScheduleStore
        from praisonaiagents.scheduler.models import ScheduleJob, Schedule
        store = FileScheduleStore(store_dir=str(tmp_path))
        job = ScheduleJob(
            name="not-due",
            schedule=Schedule(kind="every", every_seconds=9999),
            message="test",
        )
        job.last_run_at = time.time()  # Just ran
        store.add(job)
        runner = ScheduleRunner(store=store)
        due = runner.get_due_jobs()
        assert len(due) == 0

    def test_get_due_jobs_at_past(self, tmp_path):
        """One-shot 'at' jobs in the past should be due."""
        from praisonaiagents.scheduler.runner import ScheduleRunner
        from praisonaiagents.scheduler.store import FileScheduleStore
        from praisonaiagents.scheduler.models import ScheduleJob, Schedule
        store = FileScheduleStore(store_dir=str(tmp_path))
        past = "2020-01-01T00:00:00"
        job = ScheduleJob(
            name="past-at",
            schedule=Schedule(kind="at", at=past),
            message="test",
        )
        store.add(job)
        runner = ScheduleRunner(store=store)
        due = runner.get_due_jobs()
        assert len(due) == 1

    def test_disabled_job_not_due(self, tmp_path):
        from praisonaiagents.scheduler.runner import ScheduleRunner
        from praisonaiagents.scheduler.store import FileScheduleStore
        from praisonaiagents.scheduler.models import ScheduleJob, Schedule
        store = FileScheduleStore(store_dir=str(tmp_path))
        job = ScheduleJob(
            name="disabled",
            schedule=Schedule(kind="every", every_seconds=1),
            message="test",
            enabled=False,
        )
        store.add(job)
        runner = ScheduleRunner(store=store)
        due = runner.get_due_jobs()
        assert len(due) == 0


# ─── 6. Hook Event Tests ─────────────────────────────────────────────────────

class TestScheduleHookEvents:
    """Test that scheduling hook events exist."""

    def test_schedule_hook_events_exist(self):
        from praisonaiagents.hooks.types import HookEvent
        assert hasattr(HookEvent, 'SCHEDULE_ADD')
        assert hasattr(HookEvent, 'SCHEDULE_REMOVE')
        assert hasattr(HookEvent, 'SCHEDULE_TRIGGER')

    def test_schedule_hook_event_values(self):
        from praisonaiagents.hooks.types import HookEvent
        assert HookEvent.SCHEDULE_ADD.value == "schedule_add"
        assert HookEvent.SCHEDULE_REMOVE.value == "schedule_remove"
        assert HookEvent.SCHEDULE_TRIGGER.value == "schedule_trigger"


# ─── 7. Lazy Import Tests ────────────────────────────────────────────────────

class TestLazyImport:
    """Ensure schedule tools don't impact import time."""

    def test_praisonaiagents_import_no_scheduler(self):
        """Importing praisonaiagents should NOT load scheduler module."""
        # We verify by checking TOOL_MAPPINGS references lazy paths
        from praisonaiagents.tools import TOOL_MAPPINGS
        for key in ['schedule_add', 'schedule_list', 'schedule_remove']:
            assert key in TOOL_MAPPINGS
            module_path, _ = TOOL_MAPPINGS[key]
            assert module_path == '.schedule_tools'


# ─── 8. TOOL_MAPPINGS Registration Test ──────────────────────────────────────

class TestToolMappings:
    """Test schedule tools are registered in TOOL_MAPPINGS for string-name resolution."""

    def test_schedule_tools_in_mappings(self):
        from praisonaiagents.tools import TOOL_MAPPINGS
        assert 'schedule_add' in TOOL_MAPPINGS
        assert 'schedule_list' in TOOL_MAPPINGS
        assert 'schedule_remove' in TOOL_MAPPINGS

    def test_schedule_tools_lazy_loadable(self):
        """Verify tools can be lazy-loaded via __getattr__."""
        from praisonaiagents import tools
        schedule_add = getattr(tools, 'schedule_add')
        assert callable(schedule_add)
        schedule_list = getattr(tools, 'schedule_list')
        assert callable(schedule_list)
        schedule_remove = getattr(tools, 'schedule_remove')
        assert callable(schedule_remove)
