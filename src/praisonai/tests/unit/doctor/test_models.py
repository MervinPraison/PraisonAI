"""Unit tests for doctor models."""

import pytest
from praisonai.cli.features.doctor.models import (
    CheckStatus,
    CheckCategory,
    CheckSeverity,
    CheckResult,
    CheckDefinition,
    DoctorConfig,
    DoctorReport,
    ReportSummary,
    EnvironmentSummary,
)


class TestCheckStatus:
    """Tests for CheckStatus enum."""
    
    def test_status_values(self):
        """Test all status values exist."""
        assert CheckStatus.PASS.value == "pass"
        assert CheckStatus.WARN.value == "warn"
        assert CheckStatus.FAIL.value == "fail"
        assert CheckStatus.SKIP.value == "skip"
        assert CheckStatus.ERROR.value == "error"


class TestCheckCategory:
    """Tests for CheckCategory enum."""
    
    def test_category_values(self):
        """Test all category values exist."""
        assert CheckCategory.ENVIRONMENT.value == "environment"
        assert CheckCategory.CONFIG.value == "config"
        assert CheckCategory.TOOLS.value == "tools"
        assert CheckCategory.DATABASE.value == "database"
        assert CheckCategory.MCP.value == "mcp"
        assert CheckCategory.OBSERVABILITY.value == "observability"
        assert CheckCategory.SKILLS.value == "skills"
        assert CheckCategory.MEMORY.value == "memory"
        assert CheckCategory.PERMISSIONS.value == "permissions"
        assert CheckCategory.NETWORK.value == "network"
        assert CheckCategory.PERFORMANCE.value == "performance"
        assert CheckCategory.SELFTEST.value == "selftest"


class TestCheckResult:
    """Tests for CheckResult dataclass."""
    
    def test_create_result(self):
        """Test creating a check result."""
        result = CheckResult(
            id="test_check",
            title="Test Check",
            category=CheckCategory.ENVIRONMENT,
            status=CheckStatus.PASS,
            message="Test passed",
        )
        assert result.id == "test_check"
        assert result.title == "Test Check"
        assert result.status == CheckStatus.PASS
        assert result.passed is True
    
    def test_result_to_dict(self):
        """Test converting result to dictionary."""
        result = CheckResult(
            id="test_check",
            title="Test Check",
            category=CheckCategory.ENVIRONMENT,
            status=CheckStatus.PASS,
            message="Test passed",
            duration_ms=100.5,
        )
        d = result.to_dict()
        assert d["id"] == "test_check"
        assert d["status"] == "pass"
        assert d["category"] == "environment"
        assert d["duration_ms"] == 100.5
    
    def test_result_passed_property(self):
        """Test passed property for different statuses."""
        pass_result = CheckResult(
            id="test", title="Test", category=CheckCategory.ENVIRONMENT,
            status=CheckStatus.PASS, message="OK"
        )
        assert pass_result.passed is True
        
        skip_result = CheckResult(
            id="test", title="Test", category=CheckCategory.ENVIRONMENT,
            status=CheckStatus.SKIP, message="Skipped"
        )
        assert skip_result.passed is True
        
        fail_result = CheckResult(
            id="test", title="Test", category=CheckCategory.ENVIRONMENT,
            status=CheckStatus.FAIL, message="Failed"
        )
        assert fail_result.passed is False
    
    def test_result_is_failure(self):
        """Test is_failure property."""
        fail_result = CheckResult(
            id="test", title="Test", category=CheckCategory.ENVIRONMENT,
            status=CheckStatus.FAIL, message="Failed"
        )
        assert fail_result.is_failure is True
        
        error_result = CheckResult(
            id="test", title="Test", category=CheckCategory.ENVIRONMENT,
            status=CheckStatus.ERROR, message="Error"
        )
        assert error_result.is_failure is True
        
        pass_result = CheckResult(
            id="test", title="Test", category=CheckCategory.ENVIRONMENT,
            status=CheckStatus.PASS, message="OK"
        )
        assert pass_result.is_failure is False


class TestDoctorConfig:
    """Tests for DoctorConfig dataclass."""
    
    def test_default_config(self):
        """Test default configuration values."""
        config = DoctorConfig()
        assert config.deep is False
        assert config.timeout == 10.0
        assert config.strict is False
        assert config.quiet is False
        assert config.format == "text"
        assert config.mock is True
        assert config.live is False
    
    def test_custom_config(self):
        """Test custom configuration."""
        config = DoctorConfig(
            deep=True,
            timeout=30.0,
            strict=True,
            format="json",
        )
        assert config.deep is True
        assert config.timeout == 30.0
        assert config.strict is True
        assert config.format == "json"


class TestDoctorReport:
    """Tests for DoctorReport dataclass."""
    
    def test_create_report(self):
        """Test creating a report."""
        report = DoctorReport()
        assert report.version == "1.0.0"
        assert report.results == []
        assert report.exit_code == 0
    
    def test_calculate_summary(self):
        """Test calculating summary from results."""
        results = [
            CheckResult(id="1", title="T1", category=CheckCategory.ENVIRONMENT,
                       status=CheckStatus.PASS, message="OK"),
            CheckResult(id="2", title="T2", category=CheckCategory.ENVIRONMENT,
                       status=CheckStatus.PASS, message="OK"),
            CheckResult(id="3", title="T3", category=CheckCategory.ENVIRONMENT,
                       status=CheckStatus.WARN, message="Warning"),
            CheckResult(id="4", title="T4", category=CheckCategory.ENVIRONMENT,
                       status=CheckStatus.FAIL, message="Failed"),
            CheckResult(id="5", title="T5", category=CheckCategory.ENVIRONMENT,
                       status=CheckStatus.SKIP, message="Skipped"),
        ]
        report = DoctorReport(results=results)
        report.calculate_summary()
        
        assert report.summary.total == 5
        assert report.summary.passed == 2
        assert report.summary.warnings == 1
        assert report.summary.failed == 1
        assert report.summary.skipped == 1
    
    def test_calculate_exit_code(self):
        """Test exit code calculation."""
        # All pass
        report = DoctorReport(results=[
            CheckResult(id="1", title="T1", category=CheckCategory.ENVIRONMENT,
                       status=CheckStatus.PASS, message="OK"),
        ])
        report.calculate_summary()
        assert report.calculate_exit_code() == 0
        
        # Has failure
        report = DoctorReport(results=[
            CheckResult(id="1", title="T1", category=CheckCategory.ENVIRONMENT,
                       status=CheckStatus.FAIL, message="Failed"),
        ])
        report.calculate_summary()
        assert report.calculate_exit_code() == 1
        
        # Has error
        report = DoctorReport(results=[
            CheckResult(id="1", title="T1", category=CheckCategory.ENVIRONMENT,
                       status=CheckStatus.ERROR, message="Error"),
        ])
        report.calculate_summary()
        assert report.calculate_exit_code() == 2
    
    def test_calculate_exit_code_strict(self):
        """Test exit code with strict mode."""
        report = DoctorReport(results=[
            CheckResult(id="1", title="T1", category=CheckCategory.ENVIRONMENT,
                       status=CheckStatus.WARN, message="Warning"),
        ])
        report.calculate_summary()
        
        # Without strict
        assert report.calculate_exit_code(strict=False) == 0
        
        # With strict
        assert report.calculate_exit_code(strict=True) == 1
    
    def test_report_to_dict(self):
        """Test converting report to dictionary."""
        report = DoctorReport(
            results=[
                CheckResult(id="1", title="T1", category=CheckCategory.ENVIRONMENT,
                           status=CheckStatus.PASS, message="OK"),
            ]
        )
        report.calculate_summary()
        
        d = report.to_dict()
        assert "version" in d
        assert "timestamp" in d
        assert "results" in d
        assert "summary" in d
        assert len(d["results"]) == 1
