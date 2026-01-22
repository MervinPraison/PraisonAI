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
        from praisonai.train.agents.storage import TrainingStorage
        
        storage = TrainingStorage(session_id="test-session")
        
        assert storage.session_id == "test-session"
        assert "train" in str(storage.storage_path)
    
    def test_create_storage_custom_path(self):
        """Test creating storage with custom path."""
        from praisonai.train.agents.storage import TrainingStorage
        
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = TrainingStorage(
                session_id="custom-session",
                storage_dir=Path(tmpdir)
            )
            
            assert storage.storage_dir == Path(tmpdir)
    
    def test_save_iteration(self):
        """Test saving a training iteration."""
        from praisonai.train.agents.storage import TrainingStorage
        from praisonai.train.agents.models import TrainingIteration
        
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
        from praisonai.train.agents.storage import TrainingStorage
        from praisonai.train.agents.models import TrainingIteration
        
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
        from praisonai.train.agents.storage import TrainingStorage
        from praisonai.train.agents.models import TrainingIteration
        
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
        from praisonai.train.agents.storage import TrainingStorage
        
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = TrainingStorage(
                session_id="empty-test",
                storage_dir=Path(tmpdir)
            )
            
            iterations = storage.load_iterations()
            
            assert iterations == []
    
    def test_save_scenario(self):
        """Test saving a training scenario."""
        from praisonai.train.agents.storage import TrainingStorage
        from praisonai.train.agents.models import TrainingScenario
        
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
        from praisonai.train.agents.storage import TrainingStorage
        from praisonai.train.agents.models import TrainingReport
        
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
        from praisonai.train.agents.storage import TrainingStorage
        from praisonai.train.agents.models import TrainingIteration
        
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
        from praisonai.train.agents.storage import TrainingStorage, list_training_sessions
        from praisonai.train.agents.models import TrainingIteration
        
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
