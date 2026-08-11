"""
TDD Tests for Agent Training Storage.

Tests for TrainingStorage class that persists training data to JSON.
"""

import json
import tempfile
from pathlib import Path


class TestTrainingStorage:
    """Tests for TrainingStorage class."""
    
    def test_create_storage_default_path(self):
        """Test creating storage with default path."""
        from praisonai_train.train.agents.storage import TrainingStorage
        
        storage = TrainingStorage(session_id="test-session")
        
        assert storage.session_id == "test-session"
        assert "train" in str(storage.storage_path)
    
    def test_create_storage_custom_path(self):
        """Test creating storage with custom path."""
        from praisonai_train.train.agents.storage import TrainingStorage
        
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = TrainingStorage(
                session_id="custom-session",
                storage_dir=Path(tmpdir)
            )
            
            assert storage.storage_dir == Path(tmpdir)
    
    def test_save_iteration(self):
        """Test saving a training iteration."""
        from praisonai_train.train.agents.storage import TrainingStorage
        from praisonai_train.train.agents.models import TrainingIteration
        
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = TrainingStorage(
                session_id="save-test",
                storage_dir=Path(tmpdir)
            )
            
            iteration = TrainingIteration(
                iteration_num=1,
                scenario_id="s1",
                input_text="Test input",
                output="Test output",
                score=7.5,
                feedback="Good job"
            )
            
            storage.save_iteration(iteration)
            
            # Verify file exists
            assert storage.storage_path.exists()
            
            # Verify content
            with open(storage.storage_path) as f:
                data = json.load(f)
            
            assert "iterations" in data
            assert len(data["iterations"]) == 1
            assert data["iterations"][0]["score"] == 7.5
    
    def test_save_multiple_iterations(self):
        """Test saving multiple iterations."""
        from praisonai_train.train.agents.storage import TrainingStorage
        from praisonai_train.train.agents.models import TrainingIteration
        
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = TrainingStorage(
                session_id="multi-test",
                storage_dir=Path(tmpdir)
            )
            
            for i in range(3):
                iteration = TrainingIteration(
                    iteration_num=i + 1,
                    scenario_id="s1",
                    input_text=f"Input {i}",
                    output=f"Output {i}",
                    score=5.0 + i,
                    feedback=f"Feedback {i}"
                )
                storage.save_iteration(iteration)
            
            # Verify all saved
            with open(storage.storage_path) as f:
                data = json.load(f)
            
            assert len(data["iterations"]) == 3
    
    def test_load_iterations(self):
        """Test loading iterations from storage."""
        from praisonai_train.train.agents.storage import TrainingStorage
        from praisonai_train.train.agents.models import TrainingIteration
        
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = TrainingStorage(
                session_id="load-test",
                storage_dir=Path(tmpdir)
            )
            
            # Save some iterations
            for i in range(2):
                iteration = TrainingIteration(
                    iteration_num=i + 1,
                    scenario_id="s1",
                    input_text=f"Input {i}",
                    output=f"Output {i}",
                    score=6.0 + i,
                    feedback=f"Feedback {i}"
                )
                storage.save_iteration(iteration)
            
            # Load them back
            iterations = storage.load_iterations()
            
            assert len(iterations) == 2
            assert iterations[0].iteration_num == 1
            assert iterations[1].score == 7.0
    
    def test_load_empty_storage(self):
        """Test loading from empty/nonexistent storage."""
        from praisonai_train.train.agents.storage import TrainingStorage
        
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = TrainingStorage(
                session_id="empty-test",
                storage_dir=Path(tmpdir)
            )
            
            iterations = storage.load_iterations()
            
            assert iterations == []
    
    def test_save_scenario(self):
        """Test saving a training scenario."""
        from praisonai_train.train.agents.storage import TrainingStorage
        from praisonai_train.train.agents.models import TrainingScenario
        
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = TrainingStorage(
                session_id="scenario-test",
                storage_dir=Path(tmpdir)
            )
            
            scenario = TrainingScenario(
                id="s1",
                input_text="What is Python?",
                expected_output="Python is a programming language"
            )
            
            storage.save_scenario(scenario)
            
            # Verify
            with open(storage.storage_path) as f:
                data = json.load(f)
            
            assert "scenarios" in data
            assert len(data["scenarios"]) == 1
    
    def test_save_report(self):
        """Test saving a training report."""
        from praisonai_train.train.agents.storage import TrainingStorage
        from praisonai_train.train.agents.models import TrainingReport
        
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = TrainingStorage(
                session_id="report-test",
                storage_dir=Path(tmpdir)
            )
            
            report = TrainingReport(
                session_id="report-test",
                iterations=[],
                total_iterations=0
            )
            
            storage.save_report(report)
            
            # Verify
            with open(storage.storage_path) as f:
                data = json.load(f)
            
            assert "report" in data
            assert data["report"]["session_id"] == "report-test"
    
    def test_storage_uses_json_not_pickle(self):
        """Verify storage uses JSON format, not pickle."""
        from praisonai_train.train.agents.storage import TrainingStorage
        from praisonai_train.train.agents.models import TrainingIteration
        
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = TrainingStorage(
                session_id="json-test",
                storage_dir=Path(tmpdir)
            )
            
            iteration = TrainingIteration(
                iteration_num=1,
                scenario_id="s1",
                input_text="Test",
                output="Output",
                score=8.0,
                feedback="Good"
            )
            storage.save_iteration(iteration)
            
            # File should be JSON (readable as text)
            content = storage.storage_path.read_text()
            assert content.startswith("{")  # JSON starts with {
            
            # Should be valid JSON
            json.loads(content)
    
    def test_list_sessions(self):
        """Test listing all training sessions."""
        from praisonai_train.train.agents.storage import TrainingStorage, list_training_sessions
        from praisonai_train.train.agents.models import TrainingIteration
        
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            
            # Create multiple sessions
            for i in range(3):
                storage = TrainingStorage(
                    session_id=f"session-{i}",
                    storage_dir=tmppath
                )
                iteration = TrainingIteration(
                    iteration_num=1,
                    scenario_id="s1",
                    input_text="Test",
                    output="Output",
                    score=7.0,
                    feedback="OK"
                )
                storage.save_iteration(iteration)
            
            # List sessions
            sessions = list_training_sessions(storage_dir=tmppath)
            
            assert len(sessions) == 3
            assert any(s.session_id == "session-0" for s in sessions)


class TestSQLiteBackedSessions:
    """
    Tests for SQLite-backed sessions being discoverable without a JSON sidecar.

    Regression coverage for the bug where ``list``/``show``/``apply`` only
    scanned ``~/.praison/train/*.json`` and could not find sessions written
    with ``--storage-backend sqlite``.
    """

    def _make_iteration(self, num=1, score=9.0):
        from praisonai_train.train.agents.models import TrainingIteration

        return TrainingIteration(
            iteration_num=num,
            scenario_id="s1",
            input_text="hi",
            output="hello",
            score=score,
            feedback="good",
        )

    def test_exists_is_backend_aware(self):
        """TrainingStorage.exists() checks the backend, not just the JSON path."""
        from praisonaiagents.storage import SQLiteBackend
        from praisonai_train.train.agents.storage import TrainingStorage

        with tempfile.TemporaryDirectory() as tmpdir:
            db = str(Path(tmpdir) / "train.db")
            sid = "train-sqlonly"

            with TrainingStorage(session_id=sid, backend=SQLiteBackend(db_path=db)) as storage:
                storage.save_iteration(self._make_iteration())

            with TrainingStorage(session_id=sid, backend=SQLiteBackend(db_path=db)) as reopened:
                # Backend-aware existence succeeds even though no JSON sidecar exists
                assert reopened.exists() is True

    def test_list_sqlite_only_no_json_sidecar(self):
        """list_sessions_from_backend finds sessions stored only in SQLite."""
        from praisonaiagents.storage import SQLiteBackend
        from praisonai_train.train.agents.storage import (
            TrainingStorage,
            list_sessions_from_backend,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            db = str(Path(tmpdir) / "train.db")
            sid = "train-sqlonly"

            with TrainingStorage(session_id=sid, backend=SQLiteBackend(db_path=db)) as storage:
                storage.save_iteration(self._make_iteration())

            list_backend = SQLiteBackend(db_path=db)
            try:
                sessions = list_sessions_from_backend(list_backend)
            finally:
                list_backend.close()

            assert len(sessions) == 1
            assert sessions[0].session_id == sid
            assert sessions[0].iteration_count == 1

    def test_show_sqlite_without_json_gate(self):
        """A SQLite-backed session round-trips report data without a JSON file."""
        from praisonaiagents.storage import SQLiteBackend
        from praisonai_train.train.agents.storage import TrainingStorage
        from praisonai_train.train.agents.models import TrainingReport

        with tempfile.TemporaryDirectory() as tmpdir:
            db = str(Path(tmpdir) / "train.db")
            sid = "train-sqlonly"

            it = self._make_iteration()
            with TrainingStorage(session_id=sid, backend=SQLiteBackend(db_path=db)) as storage:
                storage.save_iteration(it)
                storage.save_report(
                    TrainingReport(session_id=sid, iterations=[it], total_iterations=1)
                )

            with TrainingStorage(session_id=sid, backend=SQLiteBackend(db_path=db)) as reopened:
                report = reopened.load_report()

                assert report is not None
                assert report.iterations[0].score == 9.0
                # No JSON sidecar was created for this session id
                assert not reopened.storage_path.exists()


class TestCustomFileBackedSessions:
    """
    Tests that ``--storage-backend file --storage-path <dir>`` sessions are
    discoverable by ``list``/``show``/``apply``.

    Regression coverage for the bug where ``_resolve_backend`` discarded the
    ``file`` backend's custom path, so sessions written to a custom directory
    were read from the default ``~/.praison/train`` dir instead.
    """

    def _make_iteration(self, num=1, score=8.0):
        from praisonai_train.train.agents.models import TrainingIteration

        return TrainingIteration(
            iteration_num=num,
            scenario_id="s1",
            input_text="hi",
            output="hello",
            score=score,
            feedback="good",
        )

    def test_resolve_backend_honours_custom_file_path(self):
        """file backend + custom path yields a FileBackend for that dir."""
        from praisonai_train.cli.commands.train import _resolve_backend

        class _Out:
            def print_error(self, *a, **k):
                pass

        with tempfile.TemporaryDirectory() as tmpdir:
            # No custom path -> default dir behaviour preserved (None).
            assert _resolve_backend("file", None, _Out()) is None
            # Custom path -> a real backend rooted at that dir.
            backend = _resolve_backend("file", tmpdir, _Out())
            assert backend is not None
            assert Path(backend.storage_dir) == Path(tmpdir)

    def test_custom_file_dir_round_trip(self):
        """A session written to a custom dir is found via that dir's backend."""
        from praisonaiagents.storage import FileBackend
        from praisonai_train.train.agents.storage import (
            TrainingStorage,
            list_training_sessions,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            sid = "train-customdir"

            # Simulate training with --storage-backend file --storage-path tmpdir
            storage = TrainingStorage(
                session_id=sid, backend=FileBackend(storage_dir=tmpdir)
            )
            storage.save_iteration(self._make_iteration())

            # show/apply path: backend rooted at the custom dir finds it.
            reopened = TrainingStorage(
                session_id=sid, backend=FileBackend(storage_dir=tmpdir)
            )
            assert reopened.exists() is True
            assert len(reopened.load_iterations()) == 1

            # list path: scanning the custom dir surfaces the session.
            sessions = list_training_sessions(storage_dir=Path(tmpdir))
            assert any(s.session_id == sid for s in sessions)
