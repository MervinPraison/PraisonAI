"""Unit tests for doctor formatters."""

import json
import sys
from unittest.mock import patch

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
    
    def test_unicode_encoding_safety_with_utf8(self):
        """Test that Unicode symbols are used when UTF-8 is supported."""
        formatter = TextFormatter(no_color=True)
        # Simulate a console that can encode Unicode (e.g. UTF-8).
        formatter._unicode_supported = True
        result = CheckResult(
            id="test",
            title="Test Check",
            category=CheckCategory.ENVIRONMENT,
            status=CheckStatus.PASS,
            message="OK",
        )
        output = formatter.format_result(result)
        # Should use Unicode symbol for pass
        assert "✓" in output
    
    def test_unicode_encoding_safety_with_cp1252(self):
        """Test that ASCII symbols are used when encoding doesn't support Unicode."""
        formatter = TextFormatter(no_color=True)
        # Simulate a legacy (cp1252) console that cannot encode Unicode.
        formatter._unicode_supported = False
        result = CheckResult(
            id="test",
            title="Test Check", 
            category=CheckCategory.ENVIRONMENT,
            status=CheckStatus.PASS,
            message="OK",
        )
        output = formatter.format_result(result)
        # Should use ASCII symbol for pass instead of Unicode
        assert "[OK]" in output
        assert "✓" not in output

    @staticmethod
    def _sample_report():
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
        return report

    def test_divider_uses_ascii_on_cp1252(self):
        """Divider must fall back to ASCII on legacy (cp1252) consoles."""
        formatter = TextFormatter(no_color=True)
        # Simulate a console that cannot encode Unicode.
        formatter._unicode_supported = False
        output = formatter.format_report(self._sample_report())
        # The Unicode box-drawing divider must not appear.
        assert "━" not in output
        assert "-" * 70 in output
        # Whole report must be encodable on cp1252 without errors.
        output.encode("cp1252")

    def test_divider_uses_unicode_on_utf8(self):
        """Divider should keep Unicode characters on UTF-8 consoles."""
        formatter = TextFormatter(no_color=True)
        formatter._unicode_supported = True
        output = formatter.format_report(self._sample_report())
        assert "━" in output

    def test_can_encode_unicode_detects_cp1252(self):
        """_can_encode_unicode should report False for cp1252 streams."""
        formatter = TextFormatter(no_color=True)

        class _FakeStdout:
            encoding = "cp1252"

        with patch("praisonai.cli.features.doctor.formatters.sys.stdout", _FakeStdout()):
            assert formatter._can_encode_unicode() is False

    def test_can_encode_unicode_detects_utf8(self):
        """_can_encode_unicode should report True for utf-8 streams."""
        formatter = TextFormatter(no_color=True)

        class _FakeStdout:
            encoding = "utf-8"

        with patch("praisonai.cli.features.doctor.formatters.sys.stdout", _FakeStdout()):
            assert formatter._can_encode_unicode() is True

    def test_write_does_not_crash_on_cp1252_stream(self):
        """write() must not raise UnicodeEncodeError on a strict cp1252 stream."""
        import io

        formatter = TextFormatter(no_color=True)
        # Force Unicode content even though destination can't encode it.
        formatter._unicode_supported = True
        report = self._sample_report()

        # Destination stream only supports cp1252 (strict).
        raw = io.BytesIO()
        stream = io.TextIOWrapper(raw, encoding="cp1252", errors="strict")
        # Should not raise despite Unicode content in the rendered report.
        formatter.write(report, stream)
        stream.flush()
        assert raw.getvalue()  # something was written

    def test_json_write_does_not_crash_on_cp1252_stream(self):
        """JSON write() must also be safe on a strict cp1252 stream."""
        import io

        formatter = JsonFormatter()
        report = self._sample_report()
        # Inject a Unicode character into the message to exercise the fallback.
        report.results[0].message = "café ✓"

        raw = io.BytesIO()
        stream = io.TextIOWrapper(raw, encoding="cp1252", errors="strict")
        formatter.write(report, stream)
        stream.flush()
        assert raw.getvalue()


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
