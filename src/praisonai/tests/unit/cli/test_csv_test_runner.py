"""
Tests for CSV Test Runner.

Tests CSV parsing, test execution, assertions, and reporting.
"""

import tempfile
from pathlib import Path



class TestCSVSchema:
    """Tests for CSV schema definition."""
    
    def test_schema_has_required_fields(self):
        """Test that schema defines required fields."""
        from praisonai.cli.features.csv_test_runner import CSV_SCHEMA
        
        assert "id" in CSV_SCHEMA
        assert "name" in CSV_SCHEMA
        assert "prompts" in CSV_SCHEMA
        
        assert CSV_SCHEMA["id"]["required"] is True
        assert CSV_SCHEMA["name"]["required"] is True
        assert CSV_SCHEMA["prompts"]["required"] is True
    
    def test_schema_has_optional_fields(self):
        """Test that schema defines optional fields."""
        from praisonai.cli.features.csv_test_runner import CSV_SCHEMA
        
        optional_fields = [
            "description", "mode", "workspace_fixture",
            "expected_tools", "forbidden_tools", "expected_files",
            "expected_response", "judge_rubric", "judge_threshold",
            "judge_model", "timeout", "retries", "skip_if",
            "agents", "workflow",
        ]
        
        for field in optional_fields:
            assert field in CSV_SCHEMA
            assert CSV_SCHEMA[field]["required"] is False


class TestTestCase:
    """Tests for TestCase dataclass."""
    
    def test_default_values(self):
        """Test default test case values."""
        from praisonai.cli.features.csv_test_runner import TestCase
        
        tc = TestCase(id="test1", name="Test 1", prompts=["Hello"])
        
        assert tc.mode == "headless"
        assert tc.workspace_fixture == "empty"
        assert tc.expected_tools == []
        assert tc.forbidden_tools == []
        assert tc.judge_threshold == 7.0
        assert tc.timeout == 60
    
    def test_should_skip_no_condition(self):
        """Test should_skip with no condition."""
        from praisonai.cli.features.csv_test_runner import TestCase
        
        tc = TestCase(id="test1", name="Test 1", prompts=["Hello"])
        assert tc.should_skip() is None
    
    def test_should_skip_no_openai_key(self):
        """Test should_skip with no_openai_key condition."""
        import os
        from praisonai.cli.features.csv_test_runner import TestCase
        
        tc = TestCase(
            id="test1", name="Test 1", prompts=["Hello"],
            skip_if="no_openai_key"
        )
        
        # Save and clear key
        original = os.environ.get("OPENAI_API_KEY")
        if "OPENAI_API_KEY" in os.environ:
            del os.environ["OPENAI_API_KEY"]
        
        try:
            result = tc.should_skip()
            assert result is not None
            assert "OPENAI_API_KEY" in result
        finally:
            if original:
                os.environ["OPENAI_API_KEY"] = original


class TestTestResult:
    """Tests for TestResult dataclass."""
    
    def test_to_dict(self):
        """Test result serialization."""
        from praisonai.cli.features.csv_test_runner import TestResult
        
        result = TestResult(
            test_id="test1",
            test_name="Test 1",
            status="passed",
            duration=1.5,
            tool_calls=["read_file"],
            response="Hello",
        )
        
        d = result.to_dict()
        assert d["test_id"] == "test1"
        assert d["status"] == "passed"
        assert d["duration"] == 1.5
        assert d["tool_calls"] == ["read_file"]


class TestTestSummary:
    """Tests for TestSummary dataclass."""
    
    def test_to_dict(self):
        """Test summary serialization."""
        from praisonai.cli.features.csv_test_runner import TestSummary
        
        summary = TestSummary(
            total=10,
            passed=8,
            failed=1,
            skipped=1,
            errors=0,
            duration=30.0,
        )
        
        d = summary.to_dict()
        assert d["total"] == 10
        assert d["passed"] == 8
        assert d["pass_rate"] == 0.8
    
    def test_pass_rate_zero_total(self):
        """Test pass rate with zero total."""
        from praisonai.cli.features.csv_test_runner import TestSummary
        
        summary = TestSummary(total=0)
        d = summary.to_dict()
        assert d["pass_rate"] == 0


class TestParseCSV:
    """Tests for parse_csv function."""
    
    def test_parse_simple_csv(self):
        """Test parsing simple CSV."""
        from praisonai.cli.features.csv_test_runner import parse_csv
        
        csv_content = """id,name,prompts
test1,Test One,Hello world
test2,Test Two,Goodbye world"""
        
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            f.write(csv_content)
            f.flush()
            
            test_cases = parse_csv(Path(f.name))
        
        assert len(test_cases) == 2
        assert test_cases[0].id == "test1"
        assert test_cases[0].name == "Test One"
        assert test_cases[0].prompts == ["Hello world"]
    
    def test_parse_json_prompts(self):
        """Test parsing CSV with JSON prompts array."""
        from praisonai.cli.features.csv_test_runner import parse_csv
        
        csv_content = '''id,name,prompts
test1,Multi-step,"[""Step 1"", ""Step 2""]"'''
        
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            f.write(csv_content)
            f.flush()
            
            test_cases = parse_csv(Path(f.name))
        
        assert len(test_cases) == 1
        assert test_cases[0].prompts == ["Step 1", "Step 2"]
    
    def test_parse_expected_tools(self):
        """Test parsing expected_tools column."""
        from praisonai.cli.features.csv_test_runner import parse_csv
        
        csv_content = """id,name,prompts,expected_tools
test1,Tool Test,Hello,"read_file,write_file"
"""
        
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            f.write(csv_content)
            f.flush()
            
            test_cases = parse_csv(Path(f.name))
        
        assert test_cases[0].expected_tools == ["read_file", "write_file"]
    
    def test_parse_expected_files_json(self):
        """Test parsing expected_files JSON column."""
        from praisonai.cli.features.csv_test_runner import parse_csv
        
        csv_content = '''id,name,prompts,expected_files
test1,File Test,Hello,"{""test.py"": ""print""}"
'''
        
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            f.write(csv_content)
            f.flush()
            
            test_cases = parse_csv(Path(f.name))
        
        assert test_cases[0].expected_files == {"test.py": "print"}
    
    def test_parse_agents_json(self):
        """Test parsing agents JSON column."""
        from praisonai.cli.features.csv_test_runner import parse_csv
        
        csv_content = '''id,name,prompts,agents
test1,Multi-agent,Hello,"[{""name"": ""Agent1""}]"
'''
        
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            f.write(csv_content)
            f.flush()
            
            test_cases = parse_csv(Path(f.name))
        
        assert test_cases[0].agents == [{"name": "Agent1"}]
    
    def test_parse_numeric_fields(self):
        """Test parsing numeric fields."""
        from praisonai.cli.features.csv_test_runner import parse_csv
        
        csv_content = """id,name,prompts,judge_threshold,timeout,retries
test1,Numeric,Hello,8.5,120,2
"""
        
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            f.write(csv_content)
            f.flush()
            
            test_cases = parse_csv(Path(f.name))
        
        assert test_cases[0].judge_threshold == 8.5
        assert test_cases[0].timeout == 120
        assert test_cases[0].retries == 2


class TestGenerateCSVTemplate:
    """Tests for generate_csv_template function."""
    
    def test_generates_valid_csv(self):
        """Test that template generates valid CSV."""
        from praisonai.cli.features.csv_test_runner import generate_csv_template
        
        csv_content = generate_csv_template()
        
        assert "id,name,prompts" in csv_content
        assert "smoke_01" in csv_content
        assert "tools_01" in csv_content
    
    def test_writes_to_file(self):
        """Test that template can be written to file."""
        from praisonai.cli.features.csv_test_runner import generate_csv_template
        
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            output_path = Path(f.name)
        
        generate_csv_template(output_path)
        
        assert output_path.exists()
        content = output_path.read_text()
        assert "id,name,prompts" in content


class TestCSVTestRunner:
    """Tests for CSVTestRunner class."""
    
    def test_initialization(self):
        """Test runner initialization."""
        from praisonai.cli.features.csv_test_runner import CSVTestRunner
        
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
            f.write(b"id,name,prompts\n")
            csv_path = Path(f.name)
        
        runner = CSVTestRunner(
            csv_path=csv_path,
            model="gpt-4o",
            judge_model="gpt-4o-mini",
            fail_fast=True,
            no_judge=True,
        )
        
        assert runner.model == "gpt-4o"
        assert runner.judge_model == "gpt-4o-mini"
        assert runner.fail_fast is True
        assert runner.no_judge is True
    
    def test_parse_judge_score_standard(self):
        """Test parsing standard judge score format."""
        from praisonai.cli.features.csv_test_runner import CSVTestRunner
        
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
            f.write(b"id,name,prompts\n")
            csv_path = Path(f.name)
        
        runner = CSVTestRunner(csv_path=csv_path)
        
        response = "SCORE: 8\nREASONING: Good response"
        score = runner._parse_judge_score(response)
        
        assert score == 8.0
    
    def test_parse_judge_score_decimal(self):
        """Test parsing decimal judge score."""
        from praisonai.cli.features.csv_test_runner import CSVTestRunner
        
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
            f.write(b"id,name,prompts\n")
            csv_path = Path(f.name)
        
        runner = CSVTestRunner(csv_path=csv_path)
        
        response = "SCORE: 7.5\nREASONING: Decent response"
        score = runner._parse_judge_score(response)
        
        assert score == 7.5
    
    def test_parse_judge_score_no_match(self):
        """Test parsing when no score found."""
        from praisonai.cli.features.csv_test_runner import CSVTestRunner
        
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
            f.write(b"id,name,prompts\n")
            csv_path = Path(f.name)
        
        runner = CSVTestRunner(csv_path=csv_path)
        
        response = "This response has no score"
        score = runner._parse_judge_score(response)
        
        assert score is None
