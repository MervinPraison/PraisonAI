"""Unit tests for evaluation utility functions."""

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

from praisonaiagents.eval.utils import (
    save_result_to_file,
    load_result_from_file,
    format_score,
    format_percentage,
    format_duration,
    format_memory,
    calculate_pass_rate,
)


class TestSaveResultToFile:
    """Tests for save_result_to_file function."""
    
    def test_save_with_to_dict(self):
        """Test saving result with to_dict method."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = f"{tmpdir}/result.json"
            result = MagicMock()
            result.to_dict.return_value = {"score": 8.0, "passed": True}
            
            success = save_result_to_file(result, path)
            
            assert success is True
            assert Path(path).exists()
            with open(path) as f:
                data = json.load(f)
            assert data["score"] == 8.0
    
    def test_save_with_dict_attr(self):
        """Test saving result with __dict__ attribute."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = f"{tmpdir}/result.json"
            
            class SimpleResult:
                def __init__(self):
                    self.score = 9.0
                    self.name = "test"
            
            result = SimpleResult()
            success = save_result_to_file(result, path)
            
            assert success is True
            with open(path) as f:
                data = json.load(f)
            assert data["score"] == 9.0
    
    def test_save_with_placeholders(self):
        """Test saving with path placeholders."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = f"{tmpdir}/{{name}}_{{eval_id}}.json"
            result = MagicMock()
            result.to_dict.return_value = {"score": 8.0}
            
            success = save_result_to_file(
                result, path,
                eval_id="abc123",
                name="test_eval"
            )
            
            assert success is True
            expected_path = f"{tmpdir}/test_eval_abc123.json"
            assert Path(expected_path).exists()
    
    def test_save_creates_directories(self):
        """Test that save creates parent directories."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = f"{tmpdir}/nested/dir/result.json"
            result = MagicMock()
            result.to_dict.return_value = {"score": 8.0}
            
            success = save_result_to_file(result, path)
            
            assert success is True
            assert Path(path).exists()
    
    def test_save_failure_returns_false(self):
        """Test that save failure returns False."""
        result = MagicMock()
        result.to_dict.side_effect = Exception("Test error")
        
        success = save_result_to_file(result, "/invalid/path/result.json")
        
        assert success is False


class TestLoadResultFromFile:
    """Tests for load_result_from_file function."""
    
    def test_load_existing_file(self):
        """Test loading existing result file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = f"{tmpdir}/result.json"
            data = {"score": 8.0, "passed": True}
            with open(path, 'w') as f:
                json.dump(data, f)
            
            loaded = load_result_from_file(path)
            
            assert loaded == data
    
    def test_load_nonexistent_file(self):
        """Test loading nonexistent file returns None."""
        result = load_result_from_file("/nonexistent/path/result.json")
        assert result is None
    
    def test_load_invalid_json(self):
        """Test loading invalid JSON returns None."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = f"{tmpdir}/invalid.json"
            with open(path, 'w') as f:
                f.write("not valid json")
            
            result = load_result_from_file(path)
            assert result is None


class TestFormatScore:
    """Tests for format_score function."""
    
    def test_format_default_max(self):
        """Test formatting with default max score."""
        assert format_score(8.5) == "8.5/10"
    
    def test_format_custom_max(self):
        """Test formatting with custom max score."""
        assert format_score(85.0, 100.0) == "85.0/100"
    
    def test_format_zero(self):
        """Test formatting zero score."""
        assert format_score(0.0) == "0.0/10"


class TestFormatPercentage:
    """Tests for format_percentage function."""
    
    def test_format_full(self):
        """Test formatting 100%."""
        assert format_percentage(1.0) == "100.0%"
    
    def test_format_half(self):
        """Test formatting 50%."""
        assert format_percentage(0.5) == "50.0%"
    
    def test_format_zero(self):
        """Test formatting 0%."""
        assert format_percentage(0.0) == "0.0%"
    
    def test_format_decimal(self):
        """Test formatting decimal percentage."""
        assert format_percentage(0.333) == "33.3%"


class TestFormatDuration:
    """Tests for format_duration function."""
    
    def test_format_microseconds(self):
        """Test formatting microseconds."""
        result = format_duration(0.0001)
        assert "μs" in result
    
    def test_format_milliseconds(self):
        """Test formatting milliseconds."""
        result = format_duration(0.5)
        assert "ms" in result
    
    def test_format_seconds(self):
        """Test formatting seconds."""
        result = format_duration(5.5)
        assert "s" in result
        assert "m" not in result
    
    def test_format_minutes(self):
        """Test formatting minutes."""
        result = format_duration(90.0)
        assert "m" in result


class TestFormatMemory:
    """Tests for format_memory function."""
    
    def test_format_kilobytes(self):
        """Test formatting kilobytes."""
        result = format_memory(0.5)
        assert "KB" in result
    
    def test_format_megabytes(self):
        """Test formatting megabytes."""
        result = format_memory(100.0)
        assert "MB" in result
    
    def test_format_gigabytes(self):
        """Test formatting gigabytes."""
        result = format_memory(2048.0)
        assert "GB" in result


class TestCalculatePassRate:
    """Tests for calculate_pass_rate function."""
    
    def test_all_passed(self):
        """Test 100% pass rate."""
        assert calculate_pass_rate(10, 10) == 1.0
    
    def test_none_passed(self):
        """Test 0% pass rate."""
        assert calculate_pass_rate(0, 10) == 0.0
    
    def test_half_passed(self):
        """Test 50% pass rate."""
        assert calculate_pass_rate(5, 10) == 0.5
    
    def test_zero_total(self):
        """Test with zero total."""
        assert calculate_pass_rate(0, 0) == 0.0
