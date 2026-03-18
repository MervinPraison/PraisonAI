"""
Unit tests for scheduler execution history functionality.

Tests:
- RunRecord model serialization
- FileScheduleStore.log_run() and get_history()
- ConfigYamlScheduleStore.log_run() and get_history()
- ScheduleRunner.mark_run() with history params
- History limit enforcement
- History persistence
"""

import os
import tempfile
import time


class TestRunRecordModel:
    """Tests for RunRecord dataclass."""

    def test_run_record_creation(self):
        """Test basic RunRecord creation."""
        from praisonaiagents.scheduler.models import RunRecord

        record = RunRecord(
            job_id="test123",
            job_name="Test Job",
            status="succeeded",
            result="Hello world",
            duration=1.5,
            delivered=True,
        )
        assert record.job_id == "test123"
        assert record.job_name == "Test Job"
        assert record.status == "succeeded"
        assert record.result == "Hello world"
        assert record.duration == 1.5
        assert record.delivered is True
        assert record.error is None
        assert record.timestamp > 0

    def test_run_record_to_dict(self):
        """Test RunRecord serialization to dict."""
        from praisonaiagents.scheduler.models import RunRecord

        record = RunRecord(
            job_id="abc",
            job_name="My Job",
            status="failed",
            error="Something went wrong",
            duration=0.5,
            timestamp=1234567890.0,
        )
        d = record.to_dict()
        assert d["job_id"] == "abc"
        assert d["job_name"] == "My Job"
        assert d["status"] == "failed"
        assert d["error"] == "Something went wrong"
        assert d["duration"] == 0.5
        assert d["timestamp"] == 1234567890.0
        assert d["delivered"] is False
        assert d["result"] is None

    def test_run_record_from_dict(self):
        """Test RunRecord deserialization from dict."""
        from praisonaiagents.scheduler.models import RunRecord

        d = {
            "job_id": "xyz",
            "job_name": "Restored Job",
            "status": "skipped",
            "result": "Skipped result",
            "error": None,
            "duration": 2.0,
            "delivered": False,
            "timestamp": 9999999999.0,
        }
        record = RunRecord.from_dict(d)
        assert record.job_id == "xyz"
        assert record.job_name == "Restored Job"
        assert record.status == "skipped"
        assert record.result == "Skipped result"
        assert record.duration == 2.0
        assert record.timestamp == 9999999999.0


class TestFileScheduleStoreHistory:
    """Tests for FileScheduleStore history functionality."""

    def test_log_run_creates_history(self):
        """Test that log_run adds a history record."""
        from praisonaiagents.scheduler.store import FileScheduleStore

        with tempfile.TemporaryDirectory() as tmpdir:
            store = FileScheduleStore(store_dir=tmpdir)
            assert len(store.get_history()) == 0

            store.log_run(
                job_id="job1",
                status="succeeded",
                result="Test result",
                duration=1.0,
                delivered=True,
                job_name="Test Job",
            )

            history = store.get_history()
            assert len(history) == 1
            assert history[0].job_id == "job1"
            assert history[0].status == "succeeded"
            assert history[0].result == "Test result"
            assert history[0].delivered is True

    def test_get_history_newest_first(self):
        """Test that history is returned newest first."""
        from praisonaiagents.scheduler.store import FileScheduleStore

        with tempfile.TemporaryDirectory() as tmpdir:
            store = FileScheduleStore(store_dir=tmpdir)

            store.log_run(job_id="job1", status="succeeded", job_name="First")
            time.sleep(0.01)
            store.log_run(job_id="job2", status="succeeded", job_name="Second")
            time.sleep(0.01)
            store.log_run(job_id="job3", status="succeeded", job_name="Third")

            history = store.get_history()
            assert len(history) == 3
            assert history[0].job_name == "Third"
            assert history[1].job_name == "Second"
            assert history[2].job_name == "First"

    def test_get_history_filter_by_job_id(self):
        """Test filtering history by job_id."""
        from praisonaiagents.scheduler.store import FileScheduleStore

        with tempfile.TemporaryDirectory() as tmpdir:
            store = FileScheduleStore(store_dir=tmpdir)

            store.log_run(job_id="job1", status="succeeded", job_name="Job 1 Run 1")
            store.log_run(job_id="job2", status="succeeded", job_name="Job 2 Run 1")
            store.log_run(job_id="job1", status="failed", job_name="Job 1 Run 2")

            all_history = store.get_history()
            assert len(all_history) == 3

            job1_history = store.get_history(job_id="job1")
            assert len(job1_history) == 2
            assert all(r.job_id == "job1" for r in job1_history)

    def test_get_history_limit(self):
        """Test history limit parameter."""
        from praisonaiagents.scheduler.store import FileScheduleStore

        with tempfile.TemporaryDirectory() as tmpdir:
            store = FileScheduleStore(store_dir=tmpdir)

            for i in range(10):
                store.log_run(job_id=f"job{i}", status="succeeded", job_name=f"Job {i}")

            limited = store.get_history(limit=5)
            assert len(limited) == 5

    def test_history_max_limit_enforcement(self):
        """Test that history is pruned to max_history."""
        from praisonaiagents.scheduler.store import FileScheduleStore

        with tempfile.TemporaryDirectory() as tmpdir:
            store = FileScheduleStore(store_dir=tmpdir, max_history=5)

            for i in range(10):
                store.log_run(job_id=f"job{i}", status="succeeded", job_name=f"Job {i}")

            history = store.get_history()
            assert len(history) == 5
            # Should have the 5 most recent (jobs 5-9)
            assert history[0].job_name == "Job 9"
            assert history[4].job_name == "Job 5"

    def test_history_persistence(self):
        """Test that history is persisted to disk."""
        from praisonaiagents.scheduler.store import FileScheduleStore

        with tempfile.TemporaryDirectory() as tmpdir:
            # Create store and add history
            store1 = FileScheduleStore(store_dir=tmpdir)
            store1.log_run(job_id="job1", status="succeeded", result="Result 1", job_name="Job 1")
            store1.log_run(job_id="job2", status="failed", error="Error 2", job_name="Job 2")

            # Verify file exists
            history_path = os.path.join(tmpdir, "history.json")
            assert os.path.exists(history_path)

            # Create new store and verify history is loaded
            store2 = FileScheduleStore(store_dir=tmpdir)
            history = store2.get_history()
            assert len(history) == 2
            assert history[0].job_name == "Job 2"
            assert history[1].job_name == "Job 1"

    def test_result_truncation(self):
        """Test that long results are truncated."""
        from praisonaiagents.scheduler.store import FileScheduleStore

        with tempfile.TemporaryDirectory() as tmpdir:
            store = FileScheduleStore(store_dir=tmpdir)

            long_result = "x" * 5000
            store.log_run(job_id="job1", status="succeeded", result=long_result, job_name="Job 1")

            history = store.get_history()
            assert len(history[0].result) == 2000


class TestConfigYamlScheduleStoreHistory:
    """Tests for ConfigYamlScheduleStore history functionality."""

    def test_log_run_creates_history(self):
        """Test that log_run adds a history record."""
        from praisonaiagents.scheduler.config_store import ConfigYamlScheduleStore

        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = os.path.join(tmpdir, "config.yaml")
            store = ConfigYamlScheduleStore(config_path=config_path)
            assert len(store.get_history()) == 0

            store.log_run(
                job_id="job1",
                status="succeeded",
                result="Test result",
                duration=1.0,
                delivered=True,
                job_name="Test Job",
            )

            history = store.get_history()
            assert len(history) == 1
            assert history[0].job_id == "job1"
            assert history[0].status == "succeeded"

    def test_history_persistence_yaml(self):
        """Test that history is persisted to YAML file."""
        from praisonaiagents.scheduler.config_store import ConfigYamlScheduleStore

        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = os.path.join(tmpdir, "config.yaml")

            # Create store and add history
            store1 = ConfigYamlScheduleStore(config_path=config_path)
            store1.log_run(job_id="job1", status="succeeded", job_name="Job 1")

            # Verify history file exists
            history_path = os.path.join(tmpdir, "run_history.yaml")
            assert os.path.exists(history_path)

            # Create new store and verify history is loaded
            store2 = ConfigYamlScheduleStore(config_path=config_path)
            history = store2.get_history()
            assert len(history) == 1
            assert history[0].job_id == "job1"


class TestScheduleRunnerHistory:
    """Tests for ScheduleRunner.mark_run() with history params."""

    def test_mark_run_logs_history(self):
        """Test that mark_run calls log_run on the store."""
        from praisonaiagents.scheduler.runner import ScheduleRunner
        from praisonaiagents.scheduler.store import FileScheduleStore
        from praisonaiagents.scheduler.models import ScheduleJob, Schedule

        with tempfile.TemporaryDirectory() as tmpdir:
            store = FileScheduleStore(store_dir=tmpdir)
            runner = ScheduleRunner(store)

            job = ScheduleJob(
                name="Test Job",
                schedule=Schedule(kind="every", every_seconds=60),
                message="Test message",
            )
            store.add(job)

            # Mark run with history params
            runner.mark_run(
                job,
                status="succeeded",
                result="Agent response",
                duration=2.5,
                delivered=True,
            )

            # Verify history was logged
            history = store.get_history()
            assert len(history) == 1
            assert history[0].job_id == job.id
            assert history[0].job_name == "Test Job"
            assert history[0].status == "succeeded"
            assert history[0].result == "Agent response"
            assert history[0].duration == 2.5
            assert history[0].delivered is True

    def test_mark_run_updates_last_run_at(self):
        """Test that mark_run still updates last_run_at."""
        from praisonaiagents.scheduler.runner import ScheduleRunner
        from praisonaiagents.scheduler.store import FileScheduleStore
        from praisonaiagents.scheduler.models import ScheduleJob, Schedule

        with tempfile.TemporaryDirectory() as tmpdir:
            store = FileScheduleStore(store_dir=tmpdir)
            runner = ScheduleRunner(store)

            job = ScheduleJob(
                name="Test Job",
                schedule=Schedule(kind="every", every_seconds=60),
                message="Test message",
            )
            store.add(job)
            assert job.last_run_at is None

            runner.mark_run(job, status="succeeded")

            # Verify last_run_at was updated
            updated_job = store.get(job.id)
            assert updated_job.last_run_at is not None


class TestSchedulerExports:
    """Tests for scheduler module exports."""

    def test_run_record_exported(self):
        """Test that RunRecord is exported from scheduler module."""
        from praisonaiagents.scheduler import RunRecord

        record = RunRecord(job_id="test", status="succeeded")
        assert record.job_id == "test"

    def test_all_exports_available(self):
        """Test that all expected exports are available."""
        from praisonaiagents import scheduler

        assert hasattr(scheduler, "RunRecord")
        assert hasattr(scheduler, "ScheduleJob")
        assert hasattr(scheduler, "Schedule")
        assert hasattr(scheduler, "DeliveryTarget")
        assert hasattr(scheduler, "FileScheduleStore")
        assert hasattr(scheduler, "ConfigYamlScheduleStore")
        assert hasattr(scheduler, "ScheduleRunner")
        assert hasattr(scheduler, "ScheduleStoreProtocol")
