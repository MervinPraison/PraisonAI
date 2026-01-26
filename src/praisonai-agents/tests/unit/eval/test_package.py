"""Unit tests for eval/package.py"""
from praisonaiagents.eval.package import (
    EvalCase,
    EvalResult,
    EvalReport,
    EvalPackage,
    EvalRunnerProtocol,
)


class TestEvalCase:
    """Tests for EvalCase dataclass."""
    
    def test_minimal_case(self):
        """Test creating a minimal eval case."""
        case = EvalCase(name="test", input="hello")
        assert case.name == "test"
        assert case.input == "hello"
        assert case.expected is None
        assert case.criteria == []
        assert case.metadata == {}
        assert case.timeout_seconds == 30.0
    
    def test_full_case(self):
        """Test creating a fully specified case."""
        case = EvalCase(
            name="math_test",
            input="What is 2+2?",
            expected="4",
            criteria=["accuracy", "conciseness"],
            metadata={"difficulty": "easy", "category": "math"},
            timeout_seconds=10.0
        )
        assert case.name == "math_test"
        assert case.expected == "4"
        assert len(case.criteria) == 2
        assert case.metadata["difficulty"] == "easy"
        assert case.timeout_seconds == 10.0
    
    def test_validation_empty_name(self):
        """Test validation rejects empty name."""
        try:
            EvalCase(name="", input="test")
            assert False, "Should have raised ValueError"
        except ValueError as e:
            assert "name" in str(e).lower()
    
    def test_validation_empty_input(self):
        """Test validation rejects empty input."""
        try:
            EvalCase(name="test", input="")
            assert False, "Should have raised ValueError"
        except ValueError as e:
            assert "input" in str(e).lower()
    
    def test_to_dict(self):
        """Test to_dict serialization."""
        case = EvalCase(
            name="test",
            input="hello",
            expected="world",
            criteria=["accuracy"]
        )
        d = case.to_dict()
        assert d["name"] == "test"
        assert d["input"] == "hello"
        assert d["expected"] == "world"
        assert d["criteria"] == ["accuracy"]
        assert "metadata" in d
        assert "timeout_seconds" in d
    
    def test_from_dict(self):
        """Test from_dict deserialization."""
        data = {
            "name": "test",
            "input": "hello",
            "expected": "world",
            "criteria": ["accuracy"],
            "metadata": {"key": "value"},
            "timeout_seconds": 15.0
        }
        case = EvalCase.from_dict(data)
        assert case.name == "test"
        assert case.input == "hello"
        assert case.expected == "world"
        assert case.criteria == ["accuracy"]
        assert case.metadata == {"key": "value"}
        assert case.timeout_seconds == 15.0
    
    def test_from_dict_minimal(self):
        """Test from_dict with minimal data."""
        data = {"name": "test", "input": "hello"}
        case = EvalCase.from_dict(data)
        assert case.name == "test"
        assert case.expected is None
        assert case.criteria == []
    
    def test_roundtrip(self):
        """Test to_dict/from_dict roundtrip."""
        original = EvalCase(
            name="roundtrip",
            input="test input",
            expected="expected output",
            criteria=["a", "b"],
            metadata={"x": "y"},
            timeout_seconds=20.0
        )
        restored = EvalCase.from_dict(original.to_dict())
        assert restored.name == original.name
        assert restored.input == original.input
        assert restored.expected == original.expected
        assert restored.criteria == original.criteria
        assert restored.timeout_seconds == original.timeout_seconds


class TestEvalResult:
    """Tests for EvalResult dataclass."""
    
    def test_minimal_result(self):
        """Test creating a minimal result."""
        result = EvalResult(case_name="test", passed=True, score=1.0)
        assert result.case_name == "test"
        assert result.passed is True
        assert result.score == 1.0
        assert result.actual_output is None
        assert result.error is None
        assert result.latency_ms == 0.0
        assert result.criteria_scores == {}
    
    def test_full_result(self):
        """Test creating a fully specified result."""
        result = EvalResult(
            case_name="test",
            passed=False,
            score=0.5,
            actual_output="wrong answer",
            error="Assertion failed",
            latency_ms=150.5,
            criteria_scores={"accuracy": 0.3, "format": 0.7}
        )
        assert result.passed is False
        assert result.score == 0.5
        assert result.actual_output == "wrong answer"
        assert result.error == "Assertion failed"
        assert result.latency_ms == 150.5
        assert result.criteria_scores["accuracy"] == 0.3
    
    def test_to_dict(self):
        """Test to_dict serialization."""
        result = EvalResult(
            case_name="test",
            passed=True,
            score=0.9,
            actual_output="output",
            latency_ms=100.0
        )
        d = result.to_dict()
        assert d["case_name"] == "test"
        assert d["passed"] is True
        assert d["score"] == 0.9
        assert d["actual_output"] == "output"
        assert d["latency_ms"] == 100.0
    
    def test_from_dict(self):
        """Test from_dict deserialization."""
        data = {
            "case_name": "test",
            "passed": True,
            "score": 0.95,
            "actual_output": "result",
            "error": None,
            "latency_ms": 50.0,
            "criteria_scores": {"a": 1.0}
        }
        result = EvalResult.from_dict(data)
        assert result.case_name == "test"
        assert result.passed is True
        assert result.score == 0.95
        assert result.criteria_scores == {"a": 1.0}


class TestEvalReport:
    """Tests for EvalReport dataclass."""
    
    def test_basic_report(self):
        """Test creating a basic report."""
        report = EvalReport(
            package_name="test_pkg",
            total_cases=10,
            passed_cases=8,
            failed_cases=2,
            average_score=0.85
        )
        assert report.package_name == "test_pkg"
        assert report.total_cases == 10
        assert report.passed_cases == 8
        assert report.failed_cases == 2
        assert report.average_score == 0.85
    
    def test_pass_rate(self):
        """Test pass_rate property."""
        report = EvalReport(
            package_name="test",
            total_cases=10,
            passed_cases=8,
            failed_cases=2,
            average_score=0.8
        )
        assert report.pass_rate == 0.8
    
    def test_pass_rate_zero_cases(self):
        """Test pass_rate with zero cases."""
        report = EvalReport(
            package_name="empty",
            total_cases=0,
            passed_cases=0,
            failed_cases=0,
            average_score=0.0
        )
        assert report.pass_rate == 0.0
    
    def test_all_passed_true(self):
        """Test all_passed when all pass."""
        report = EvalReport(
            package_name="perfect",
            total_cases=5,
            passed_cases=5,
            failed_cases=0,
            average_score=1.0
        )
        assert report.all_passed is True
    
    def test_all_passed_false(self):
        """Test all_passed when some fail."""
        report = EvalReport(
            package_name="partial",
            total_cases=5,
            passed_cases=4,
            failed_cases=1,
            average_score=0.9
        )
        assert report.all_passed is False
    
    def test_to_dict(self):
        """Test to_dict serialization."""
        result = EvalResult(case_name="c1", passed=True, score=1.0)
        report = EvalReport(
            package_name="test",
            total_cases=1,
            passed_cases=1,
            failed_cases=0,
            average_score=1.0,
            results=[result],
            thresholds_met={"accuracy": True}
        )
        d = report.to_dict()
        assert d["package_name"] == "test"
        assert d["pass_rate"] == 1.0
        assert len(d["results"]) == 1
        assert d["thresholds_met"]["accuracy"] is True


class TestEvalPackage:
    """Tests for EvalPackage dataclass."""
    
    def test_minimal_package(self):
        """Test creating a minimal package."""
        pkg = EvalPackage(name="test")
        assert pkg.name == "test"
        assert pkg.description == ""
        assert pkg.version == "1.0.0"
        assert pkg.cases == []
        assert pkg.thresholds == {}
        assert pkg.seed is None
        assert len(pkg) == 0
    
    def test_full_package(self):
        """Test creating a fully specified package."""
        case = EvalCase(name="c1", input="test")
        pkg = EvalPackage(
            name="full_pkg",
            description="A test package",
            version="2.0.0",
            cases=[case],
            thresholds={"accuracy": 0.9},
            seed=42
        )
        assert pkg.name == "full_pkg"
        assert pkg.description == "A test package"
        assert pkg.version == "2.0.0"
        assert len(pkg) == 1
        assert pkg.thresholds["accuracy"] == 0.9
        assert pkg.seed == 42
    
    def test_validation_empty_name(self):
        """Test validation rejects empty name."""
        try:
            EvalPackage(name="")
            assert False, "Should have raised ValueError"
        except ValueError as e:
            assert "name" in str(e).lower()
    
    def test_add_case(self):
        """Test add_case method."""
        pkg = EvalPackage(name="test")
        case = EvalCase(name="c1", input="test")
        pkg.add_case(case)
        assert len(pkg) == 1
        assert pkg.cases[0].name == "c1"
    
    def test_add_cases(self):
        """Test add_cases method."""
        pkg = EvalPackage(name="test")
        cases = [
            EvalCase(name="c1", input="test1"),
            EvalCase(name="c2", input="test2")
        ]
        pkg.add_cases(cases)
        assert len(pkg) == 2
    
    def test_to_dict(self):
        """Test to_dict serialization."""
        case = EvalCase(name="c1", input="test")
        pkg = EvalPackage(
            name="test",
            description="desc",
            cases=[case],
            seed=123
        )
        d = pkg.to_dict()
        assert d["name"] == "test"
        assert d["description"] == "desc"
        assert len(d["cases"]) == 1
        assert d["seed"] == 123
    
    def test_from_dict(self):
        """Test from_dict deserialization."""
        data = {
            "name": "test_pkg",
            "description": "Test package",
            "version": "2.0.0",
            "cases": [{"name": "c1", "input": "test"}],
            "thresholds": {"accuracy": 0.9},
            "seed": 42
        }
        pkg = EvalPackage.from_dict(data)
        assert pkg.name == "test_pkg"
        assert pkg.version == "2.0.0"
        assert len(pkg.cases) == 1
        assert pkg.cases[0].name == "c1"
        assert pkg.thresholds["accuracy"] == 0.9
        assert pkg.seed == 42
    
    def test_roundtrip(self):
        """Test to_dict/from_dict roundtrip."""
        original = EvalPackage(
            name="roundtrip",
            description="Test",
            version="3.0.0",
            cases=[EvalCase(name="c1", input="test")],
            thresholds={"x": 0.5},
            seed=99
        )
        restored = EvalPackage.from_dict(original.to_dict())
        assert restored.name == original.name
        assert restored.version == original.version
        assert len(restored.cases) == len(original.cases)
        assert restored.seed == original.seed


class TestEvalRunnerProtocol:
    """Tests for EvalRunnerProtocol."""
    
    def test_protocol_methods_exist(self):
        """Test protocol has required methods."""
        assert hasattr(EvalRunnerProtocol, "run")
        assert hasattr(EvalRunnerProtocol, "run_async")
