"""Unit tests for doctor formatters."""

import json

from praisonai.cli.features.doctor.models import (
    CheckCategory,
    CheckResult,
    CheckStatus,
    DoctorReport,
)
from praisonai.cli.features.doctor.formatters import (
    redact_secrets,
    redact_dict,
    TextFormatter,
    JsonFormatter,
    get_formatter,
)


class TestRedactSecrets:
    """Tests for secret redaction."""
    
    def test_redact_openai_key(self):
        """Test redacting OpenAI API key."""
        text = "Key: sk-1234567890abcdefghijklmnop"
        result = redact_secrets(text)
        assert "sk-1234567890" not in result
        assert "REDACTED" in result
    
    def test_redact_anthropic_key(self):
        """Test redacting Anthropic API key."""
        text = "Key: sk-ant-api03-abcdefghijklmnopqrstuvwxyz"
        result = redact_secrets(text)
        assert "sk-ant-api03" not in result
        assert "REDACTED" in result
    
    def test_redact_with_prefix_suffix(self):
        """Test redacting with prefix/suffix shown."""
        text = "Key: sk-1234567890abcdefghijklmnop"
        result = redact_secrets(text, show_prefix_suffix=True)
        # Should show first 4 and last 4 chars
        assert "..." in result
    
    def test_no_redaction_for_normal_text(self):
        """Test that normal text is not redacted."""
        text = "Hello world, this is a test"
        result = redact_secrets(text)
        assert result == text


class TestRedactDict:
    """Tests for dictionary redaction."""
    
    def test_redact_api_key_field(self):
        """Test redacting API key fields."""
        data = {"api_key": "sk-1234567890abcdefghijklmnop"}
        result = redact_dict(data)
        assert "REDACTED" in result["api_key"]
    
    def test_redact_nested_dict(self):
        """Test redacting nested dictionaries."""
        data = {
            "config": {
                "secret_token": "mysecrettoken12345678"
            }
        }
        result = redact_dict(data)
        assert "REDACTED" in result["config"]["secret_token"]
    
    def test_preserve_non_secret_fields(self):
        """Test that non-secret fields are preserved."""
        data = {"name": "test", "value": 123}
        result = redact_dict(data)
        assert result["name"] == "test"
        assert result["value"] == 123


class TestTextFormatter:
    """Tests for TextFormatter."""
    
    def test_format_pass_result(self):
        """Test formatting a passing result."""
        formatter = TextFormatter(no_color=True)
        result = CheckResult(
            id="test",
            title="Test Check",
            category=CheckCategory.ENVIRONMENT,
            status=CheckStatus.PASS,
            message="All good",
        )
        output = formatter.format_result(result)
        assert "Test Check" in output
        assert "All good" in output
    
    def test_format_fail_result_with_remediation(self):
        """Test formatting a failing result with remediation."""
        formatter = TextFormatter(no_color=True)
        result = CheckResult(
            id="test",
            title="Test Check",
            category=CheckCategory.ENVIRONMENT,
            status=CheckStatus.FAIL,
            message="Something wrong",
            remediation="Fix it by doing X",
        )
        output = formatter.format_result(result)
        assert "Test Check" in output
        assert "Something wrong" in output
        assert "Fix it by doing X" in output
    
    def test_format_report(self):
        """Test formatting a complete report."""
        formatter = TextFormatter(no_color=True)
        report = DoctorReport(
            results=[
                CheckResult(
                    id="test1",
                    title="Test 1",
                    category=CheckCategory.ENVIRONMENT,
                    status=CheckStatus.PASS,
                    message="OK",
                ),
                CheckResult(
                    id="test2",
                    title="Test 2",
                    category=CheckCategory.ENVIRONMENT,
                    status=CheckStatus.FAIL,
                    message="Failed",
                ),
            ]
        )
        report.calculate_summary()
        
        output = formatter.format_report(report)
        assert "Test 1" in output
        assert "Test 2" in output
        assert "1 passed" in output
        assert "1 failed" in output
    
    def test_quiet_mode(self):
        """Test quiet mode output."""
        formatter = TextFormatter(no_color=True, quiet=True)
        report = DoctorReport(
            results=[
                CheckResult(
                    id="test",
                    title="Test",
                    category=CheckCategory.ENVIRONMENT,
                    status=CheckStatus.PASS,
                    message="OK",
                ),
            ]
        )
        report.calculate_summary()
        
        output = formatter.format_report(report)
        # Should not have header in quiet mode
        assert "PraisonAI Doctor" not in output


class TestJsonFormatter:
    """Tests for JsonFormatter."""
    
    def test_format_result_json(self):
        """Test formatting a result as JSON."""
        formatter = JsonFormatter()
        result = CheckResult(
            id="test",
            title="Test Check",
            category=CheckCategory.ENVIRONMENT,
            status=CheckStatus.PASS,
            message="OK",
        )
        output = formatter.format_result(result)
        data = json.loads(output)
        assert data["id"] == "test"
        assert data["status"] == "pass"
    
    def test_format_report_json(self):
        """Test formatting a report as JSON."""
        formatter = JsonFormatter()
        report = DoctorReport(
            results=[
                CheckResult(
                    id="test",
                    title="Test",
                    category=CheckCategory.ENVIRONMENT,
                    status=CheckStatus.PASS,
                    message="OK",
                ),
            ]
        )
        report.calculate_summary()
        
        output = formatter.format_report(report)
        data = json.loads(output)
        
        assert "version" in data
        assert "results" in data
        assert "summary" in data
        assert len(data["results"]) == 1
    
    def test_json_deterministic_ordering(self):
        """Test that JSON output has deterministic ordering."""
        formatter = JsonFormatter()
        report = DoctorReport(
            results=[
                CheckResult(
                    id="b_test",
                    title="B Test",
                    category=CheckCategory.ENVIRONMENT,
                    status=CheckStatus.PASS,
                    message="OK",
                ),
                CheckResult(
                    id="a_test",
                    title="A Test",
                    category=CheckCategory.ENVIRONMENT,
                    status=CheckStatus.PASS,
                    message="OK",
                ),
            ]
        )
        report.calculate_summary()
        
        output1 = formatter.format_report(report)
        output2 = formatter.format_report(report)
        
        # Should be identical (deterministic)
        assert output1 == output2


class TestGetFormatter:
    """Tests for get_formatter function."""
    
    def test_get_text_formatter(self):
        """Test getting text formatter."""
        formatter = get_formatter("text")
        assert isinstance(formatter, TextFormatter)
    
    def test_get_json_formatter(self):
        """Test getting JSON formatter."""
        formatter = get_formatter("json")
        assert isinstance(formatter, JsonFormatter)
    
    def test_formatter_options(self):
        """Test formatter options are passed through."""
        formatter = get_formatter("text", no_color=True, quiet=True)
        assert formatter.no_color is True
        assert formatter.quiet is True
