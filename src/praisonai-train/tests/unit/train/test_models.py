"""
TDD Tests for Agent Training Models.

Tests for TrainingScenario, TrainingIteration, and TrainingReport dataclasses.
"""

from datetime import datetime


class TestTrainingScenario:
    """Tests for TrainingScenario dataclass."""
    
    def test_create_scenario_minimal(self):
        """Test creating scenario with minimal required fields."""
        from praisonai_train.train.agents.models import TrainingScenario
        
        scenario = TrainingScenario(
            id="test-1",
            input_text="What is 2+2?"
        )
        
        assert scenario.id == "test-1"
        assert scenario.input_text == "What is 2+2?"
        assert scenario.expected_output is None
        assert scenario.context == {}
    
    def test_create_scenario_full(self):
        """Test creating scenario with all fields."""
        from praisonai_train.train.agents.models import TrainingScenario
        
        scenario = TrainingScenario(
            id="test-2",
            input_text="Explain quantum computing",
            expected_output="Quantum computing uses qubits...",
            context={"domain": "science", "difficulty": "advanced"}
        )
        
        assert scenario.id == "test-2"
        assert scenario.expected_output == "Quantum computing uses qubits..."
        assert scenario.context["domain"] == "science"
    
    def test_scenario_to_dict(self):
        """Test converting scenario to dictionary."""
        from praisonai_train.train.agents.models import TrainingScenario
        
        scenario = TrainingScenario(
            id="test-3",
            input_text="Hello"
        )
        
        d = scenario.to_dict()
        assert d["id"] == "test-3"
        assert d["input_text"] == "Hello"
        assert "expected_output" in d
    
    def test_scenario_from_dict(self):
        """Test creating scenario from dictionary."""
        from praisonai_train.train.agents.models import TrainingScenario
        
        data = {
            "id": "test-4",
            "input_text": "Test input",
            "expected_output": "Test output"
        }
        
        scenario = TrainingScenario.from_dict(data)
        assert scenario.id == "test-4"
        assert scenario.input_text == "Test input"


class TestTrainingIteration:
    """Tests for TrainingIteration dataclass."""
    
    def test_create_iteration(self):
        """Test creating a training iteration."""
        from praisonai_train.train.agents.models import TrainingIteration
        
        iteration = TrainingIteration(
            iteration_num=1,
            scenario_id="test-1",
            input_text="What is AI?",
            output="AI is artificial intelligence...",
            score=8.5,
            feedback="Good explanation but could be more concise",
            suggestions=["Be more concise", "Add examples"]
        )
        
        assert iteration.iteration_num == 1
        assert iteration.scenario_id == "test-1"
        assert iteration.score == 8.5
        assert len(iteration.suggestions) == 2
    
    def test_iteration_has_timestamp(self):
        """Test that iteration has timestamp."""
        from praisonai_train.train.agents.models import TrainingIteration
        
        iteration = TrainingIteration(
            iteration_num=1,
            scenario_id="test-1",
            input_text="Test",
            output="Output",
            score=7.0,
            feedback="OK"
        )
        
        assert iteration.timestamp is not None
        # Should be a valid ISO format string
        datetime.fromisoformat(iteration.timestamp)
    
    def test_iteration_to_dict(self):
        """Test converting iteration to dictionary."""
        from praisonai_train.train.agents.models import TrainingIteration
        
        iteration = TrainingIteration(
            iteration_num=2,
            scenario_id="test-2",
            input_text="Input",
            output="Output",
            score=9.0,
            feedback="Excellent"
        )
        
        d = iteration.to_dict()
        assert d["iteration_num"] == 2
        assert d["score"] == 9.0
        assert "timestamp" in d


class TestTrainingReport:
    """Tests for TrainingReport dataclass."""
    
    def test_create_report(self):
        """Test creating a training report."""
        from praisonai_train.train.agents.models import TrainingReport, TrainingIteration
        
        iterations = [
            TrainingIteration(
                iteration_num=1,
                scenario_id="s1",
                input_text="Test",
                output="Output 1",
                score=6.0,
                feedback="Needs improvement"
            ),
            TrainingIteration(
                iteration_num=2,
                scenario_id="s1",
                input_text="Test",
                output="Output 2",
                score=8.0,
                feedback="Better"
            ),
        ]
        
        report = TrainingReport(
            session_id="train-abc123",
            iterations=iterations,
            total_iterations=2
        )
        
        assert report.session_id == "train-abc123"
        assert len(report.iterations) == 2
        assert report.total_iterations == 2
    
    def test_report_avg_score(self):
        """Test calculating average score."""
        from praisonai_train.train.agents.models import TrainingReport, TrainingIteration
        
        iterations = [
            TrainingIteration(iteration_num=1, scenario_id="s1", input_text="T", output="O", score=6.0, feedback="F"),
            TrainingIteration(iteration_num=2, scenario_id="s1", input_text="T", output="O", score=8.0, feedback="F"),
            TrainingIteration(iteration_num=3, scenario_id="s1", input_text="T", output="O", score=10.0, feedback="F"),
        ]
        
        report = TrainingReport(session_id="test", iterations=iterations, total_iterations=3)
        
        assert report.avg_score == 8.0  # (6+8+10)/3
    
    def test_report_improvement(self):
        """Test calculating improvement from first to last."""
        from praisonai_train.train.agents.models import TrainingReport, TrainingIteration
        
        iterations = [
            TrainingIteration(iteration_num=1, scenario_id="s1", input_text="T", output="O", score=5.0, feedback="F"),
            TrainingIteration(iteration_num=2, scenario_id="s1", input_text="T", output="O", score=7.0, feedback="F"),
            TrainingIteration(iteration_num=3, scenario_id="s1", input_text="T", output="O", score=9.0, feedback="F"),
        ]
        
        report = TrainingReport(session_id="test", iterations=iterations, total_iterations=3)
        
        assert report.improvement == 4.0  # 9.0 - 5.0
    
    def test_report_to_dict(self):
        """Test converting report to dictionary."""
        from praisonai_train.train.agents.models import TrainingReport
        
        report = TrainingReport(
            session_id="test-session",
            iterations=[],
            total_iterations=0
        )
        
        d = report.to_dict()
        assert d["session_id"] == "test-session"
        assert "avg_score" in d
        assert "improvement" in d
    
    def test_report_empty_iterations(self):
        """Test report with no iterations."""
        from praisonai_train.train.agents.models import TrainingReport
        
        report = TrainingReport(
            session_id="empty",
            iterations=[],
            total_iterations=0
        )
        
        assert report.avg_score == 0.0
        assert report.improvement == 0.0


class TestConsoleEncoding:
    """Tests for Windows cp1252-safe console output (issue #3040)."""

    def _make_report(self, score):
        from praisonai_train.train.agents.models import TrainingReport, TrainingIteration
        iterations = [
            TrainingIteration(
                iteration_num=1, scenario_id="s1", input_text="T",
                output="O", score=score, feedback="F",
            )
        ]
        return TrainingReport(session_id="train-abc", iterations=iterations, total_iterations=1)

    def test_console_supports_unicode_utf8(self, monkeypatch):
        import sys
        from praisonai_train.train.agents import models

        class _Stdout:
            encoding = "utf-8"

        monkeypatch.setattr(sys, "stdout", _Stdout())
        assert models.console_supports_unicode() is True

    def test_console_supports_unicode_cp1252(self, monkeypatch):
        import sys
        from praisonai_train.train.agents import models

        class _Stdout:
            encoding = "cp1252"

        monkeypatch.setattr(sys, "stdout", _Stdout())
        assert models.console_supports_unicode() is False

    def test_status_label_ascii_on_cp1252(self, monkeypatch):
        import sys
        from praisonai_train.train.agents import models

        class _Stdout:
            encoding = "cp1252"

        monkeypatch.setattr(sys, "stdout", _Stdout())
        report = self._make_report(10.0)
        label = report._status_label()
        assert label == "PASSED"
        label.encode("cp1252")  # must not raise

    def test_status_label_emoji_on_utf8(self, monkeypatch):
        import sys
        from praisonai_train.train.agents import models

        class _Stdout:
            encoding = "utf-8"

        monkeypatch.setattr(sys, "stdout", _Stdout())
        report = self._make_report(2.0)
        assert "❌" in report._status_label()

    def test_print_summary_no_raise_on_cp1252(self, monkeypatch):
        import io
        import sys
        from praisonai_train.train.agents import models

        class _Cp1252Stdout:
            encoding = "cp1252"

            def __init__(self):
                self._buf = io.BytesIO()

            def write(self, s):
                self._buf.write(s.encode("cp1252", errors="strict"))
                return len(s)

            def flush(self):
                pass

            def isatty(self):
                return False

        monkeypatch.setattr(sys, "stdout", _Cp1252Stdout())

        report = self._make_report(10.0)
        report.print_summary()  # must not raise UnicodeEncodeError
