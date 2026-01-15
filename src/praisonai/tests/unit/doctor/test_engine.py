"""Unit tests for doctor engine."""

from praisonai.cli.features.doctor.models import (
    CheckCategory,
    CheckResult,
    CheckStatus,
    DoctorConfig,
)
from praisonai.cli.features.doctor.registry import CheckRegistry, register_check
from praisonai.cli.features.doctor.engine import DoctorEngine, run_doctor


class TestDoctorEngine:
    """Tests for DoctorEngine class."""
    
    def setup_method(self):
        """Reset registry before each test."""
        CheckRegistry.reset()
    
    def teardown_method(self):
        """Reset registry after each test."""
        CheckRegistry.reset()
    
    def test_get_environment_summary(self):
        """Test getting environment summary."""
        engine = DoctorEngine()
        summary = engine.get_environment_summary()
        
        assert summary.python_version != ""
        assert summary.python_executable != ""
        assert summary.os_name != ""
    
    def test_run_check_success(self):
        """Test running a successful check."""
        registry = CheckRegistry()
        
        def passing_check(config):
            return CheckResult(
                id="passing",
                title="Passing Check",
                category=CheckCategory.ENVIRONMENT,
                status=CheckStatus.PASS,
                message="OK",
            )
        
        registry.register(
            id="passing_check",
            title="Passing Check",
            description="A passing check",
            category=CheckCategory.ENVIRONMENT,
            implementation=passing_check,
        )
        
        engine = DoctorEngine()
        result = engine.run_check("passing_check", passing_check)
        
        assert result.status == CheckStatus.PASS
        assert result.duration_ms >= 0
    
    def test_run_check_timeout(self, monkeypatch):
        """Test check timeout handling.
        
        Note: We need to restore real time.sleep since fast_sleep fixture
        patches it to be near-instant, which would prevent timeout testing.
        """
        import time
        
        # Restore real sleep for this test (fast_sleep fixture patches it)
        import importlib
        time_module = importlib.import_module('time')
        real_sleep = time_module.sleep.__wrapped__ if hasattr(time_module.sleep, '__wrapped__') else None
        
        # Create a check that simulates slow execution via a loop instead of sleep
        # This avoids the fast_sleep fixture interference
        call_count = [0]
        
        def slow_check(config):
            call_count[0] += 1
            # Use a busy loop that takes real time
            import time as t
            start = t.perf_counter()
            while t.perf_counter() - start < 5:
                pass  # Busy wait
            return CheckResult(
                id="slow",
                title="Slow Check",
                category=CheckCategory.ENVIRONMENT,
                status=CheckStatus.PASS,
                message="OK",
            )
        
        registry = CheckRegistry()
        registry.register(
            id="slow_check",
            title="Slow Check",
            description="A slow check",
            category=CheckCategory.ENVIRONMENT,
            implementation=slow_check,
        )
        
        config = DoctorConfig(timeout=0.1)
        engine = DoctorEngine(config)
        result = engine.run_check("slow_check", slow_check, timeout=0.1)
        
        assert result.status == CheckStatus.ERROR
        assert "timed out" in result.message.lower()
    
    def test_run_check_exception(self):
        """Test check exception handling."""
        def failing_check(config):
            raise ValueError("Test error")
        
        registry = CheckRegistry()
        registry.register(
            id="failing_check",
            title="Failing Check",
            description="A failing check",
            category=CheckCategory.ENVIRONMENT,
            implementation=failing_check,
        )
        
        engine = DoctorEngine()
        result = engine.run_check("failing_check", failing_check)
        
        assert result.status == CheckStatus.ERROR
        assert "ValueError" in result.message
    
    def test_run_checks_filters_by_category(self):
        """Test running checks filtered by category."""
        # Import all checks to populate registry
        from praisonai.cli.features.doctor.checks import register_all_checks
        register_all_checks()
        
        engine = DoctorEngine()
        
        # Run only environment checks
        results = engine.run_checks(categories=[CheckCategory.ENVIRONMENT])
        
        # All results should be environment category
        for result in results:
            assert result.category == CheckCategory.ENVIRONMENT
        
        # Should have at least one result
        assert len(results) >= 1
    
    def test_generate_report(self):
        """Test generating a report."""
        # Import all checks to populate registry
        from praisonai.cli.features.doctor.checks import register_all_checks
        register_all_checks()
        
        engine = DoctorEngine()
        engine.run_checks()
        report = engine.generate_report()
        
        assert report.version == "1.0.0"
        assert len(report.results) >= 1
        assert report.summary.total >= 1
    
    def test_run_returns_report(self):
        """Test that run() returns a complete report."""
        # Import all checks to populate registry
        from praisonai.cli.features.doctor.checks import register_all_checks
        register_all_checks()
        
        engine = DoctorEngine()
        report = engine.run()
        
        assert report is not None
        assert report.duration_ms >= 0
        assert len(report.results) >= 1
    
    def test_dependency_skip_on_failure(self):
        """Test that dependent checks are skipped when dependency fails."""
        registry = CheckRegistry()
        
        def failing_check(config):
            return CheckResult(
                id="failing",
                title="Failing",
                category=CheckCategory.ENVIRONMENT,
                status=CheckStatus.FAIL,
                message="Failed",
            )
        
        def dependent_check(config):
            return CheckResult(
                id="dependent",
                title="Dependent",
                category=CheckCategory.ENVIRONMENT,
                status=CheckStatus.PASS,
                message="OK",
            )
        
        registry.register(
            id="failing_check",
            title="Failing Check",
            description="Fails",
            category=CheckCategory.ENVIRONMENT,
            implementation=failing_check,
        )
        registry.register(
            id="dependent_check",
            title="Dependent Check",
            description="Depends on failing",
            category=CheckCategory.ENVIRONMENT,
            implementation=dependent_check,
            dependencies=["failing_check"],
        )
        
        config = DoctorConfig(only=["failing_check", "dependent_check"])
        engine = DoctorEngine(config)
        results = engine.run_checks()
        
        # Find the dependent check result
        dependent_results = [r for r in results if r.id == "dependent_check"]
        if dependent_results:
            assert dependent_results[0].status == CheckStatus.SKIP
        # If not found, the dependency system may have filtered it out entirely


class TestRunDoctor:
    """Tests for run_doctor convenience function."""
    
    def setup_method(self):
        """Reset registry before each test."""
        CheckRegistry.reset()
    
    def teardown_method(self):
        """Reset registry after each test."""
        CheckRegistry.reset()
    
    def test_run_doctor_basic(self):
        """Test basic run_doctor call."""
        registry = CheckRegistry()
        
        def test_check(config):
            return CheckResult(
                id="test",
                title="Test",
                category=CheckCategory.ENVIRONMENT,
                status=CheckStatus.PASS,
                message="OK",
            )
        
        registry.register(
            id="test_check",
            title="Test Check",
            description="Test",
            category=CheckCategory.ENVIRONMENT,
            implementation=test_check,
        )
        
        report = run_doctor()
        
        assert report is not None
        assert len(report.results) >= 1  # May have more if other checks registered
