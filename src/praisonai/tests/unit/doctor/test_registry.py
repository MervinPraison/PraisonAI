"""Unit tests for doctor registry."""

from praisonai.cli.features.doctor.models import (
    CheckCategory,
    CheckSeverity,
    CheckResult,
    CheckStatus,
    DoctorConfig,
)
from praisonai.cli.features.doctor.registry import (
    CheckRegistry,
    register_check,
    get_registry,
)


class TestCheckRegistry:
    """Tests for CheckRegistry class."""
    
    def setup_method(self):
        """Reset registry before each test."""
        CheckRegistry.reset()
    
    def test_singleton_pattern(self):
        """Test registry is a singleton."""
        reg1 = CheckRegistry()
        reg2 = CheckRegistry()
        assert reg1 is reg2
    
    def test_register_check(self):
        """Test registering a check."""
        registry = CheckRegistry()
        
        def dummy_check(config):
            return CheckResult(
                id="dummy",
                title="Dummy",
                category=CheckCategory.ENVIRONMENT,
                status=CheckStatus.PASS,
                message="OK",
            )
        
        registry.register(
            id="dummy_check",
            title="Dummy Check",
            description="A dummy check",
            category=CheckCategory.ENVIRONMENT,
            implementation=dummy_check,
        )
        
        assert "dummy_check" in registry.get_check_ids()
        assert registry.get_check("dummy_check") is not None
        assert registry.get_implementation("dummy_check") is not None
    
    def test_get_checks_by_category(self):
        """Test getting checks by category."""
        registry = CheckRegistry()
        
        def env_check(config):
            return CheckResult(
                id="env", title="Env", category=CheckCategory.ENVIRONMENT,
                status=CheckStatus.PASS, message="OK"
            )
        
        def config_check(config):
            return CheckResult(
                id="config", title="Config", category=CheckCategory.CONFIG,
                status=CheckStatus.PASS, message="OK"
            )
        
        registry.register(
            id="env_check", title="Env Check", description="Env",
            category=CheckCategory.ENVIRONMENT, implementation=env_check
        )
        registry.register(
            id="config_check", title="Config Check", description="Config",
            category=CheckCategory.CONFIG, implementation=config_check
        )
        
        env_checks = registry.get_checks_by_category(CheckCategory.ENVIRONMENT)
        assert len(env_checks) == 1
        assert env_checks[0].id == "env_check"
    
    def test_filter_checks_only(self):
        """Test filtering checks with only parameter."""
        registry = CheckRegistry()
        
        for i in range(3):
            registry.register(
                id=f"check_{i}",
                title=f"Check {i}",
                description=f"Check {i}",
                category=CheckCategory.ENVIRONMENT,
                implementation=lambda c: None,
            )
        
        filtered = registry.filter_checks(only=["check_0", "check_2"])
        assert len(filtered) == 2
        ids = [c.id for c in filtered]
        assert "check_0" in ids
        assert "check_2" in ids
        assert "check_1" not in ids
    
    def test_filter_checks_skip(self):
        """Test filtering checks with skip parameter."""
        registry = CheckRegistry()
        
        for i in range(3):
            registry.register(
                id=f"check_{i}",
                title=f"Check {i}",
                description=f"Check {i}",
                category=CheckCategory.ENVIRONMENT,
                implementation=lambda c: None,
            )
        
        filtered = registry.filter_checks(skip=["check_1"])
        assert len(filtered) == 2
        ids = [c.id for c in filtered]
        assert "check_0" in ids
        assert "check_2" in ids
        assert "check_1" not in ids
    
    def test_filter_checks_deep_mode(self):
        """Test filtering checks by deep mode."""
        registry = CheckRegistry()
        
        registry.register(
            id="fast_check",
            title="Fast Check",
            description="Fast",
            category=CheckCategory.ENVIRONMENT,
            implementation=lambda c: None,
            requires_deep=False,
        )
        registry.register(
            id="deep_check",
            title="Deep Check",
            description="Deep",
            category=CheckCategory.ENVIRONMENT,
            implementation=lambda c: None,
            requires_deep=True,
        )
        
        # Without deep mode
        filtered = registry.filter_checks(deep_mode=False)
        assert len(filtered) == 1
        assert filtered[0].id == "fast_check"
        
        # With deep mode
        filtered = registry.filter_checks(deep_mode=True)
        assert len(filtered) == 2
    
    def test_resolve_dependencies(self):
        """Test dependency resolution."""
        registry = CheckRegistry()
        
        registry.register(
            id="check_a",
            title="Check A",
            description="A",
            category=CheckCategory.ENVIRONMENT,
            implementation=lambda c: None,
            dependencies=[],
        )
        registry.register(
            id="check_b",
            title="Check B",
            description="B",
            category=CheckCategory.ENVIRONMENT,
            implementation=lambda c: None,
            dependencies=["check_a"],
        )
        registry.register(
            id="check_c",
            title="Check C",
            description="C",
            category=CheckCategory.ENVIRONMENT,
            implementation=lambda c: None,
            dependencies=["check_b"],
        )
        
        ordered = registry.resolve_dependencies(["check_c", "check_a", "check_b"])
        
        # check_a should come before check_b, check_b before check_c
        assert ordered.index("check_a") < ordered.index("check_b")
        assert ordered.index("check_b") < ordered.index("check_c")


class TestRegisterCheckDecorator:
    """Tests for register_check decorator."""
    
    def setup_method(self):
        """Reset registry before each test."""
        CheckRegistry.reset()
    
    def test_decorator_registers_check(self):
        """Test that decorator registers the check."""
        @register_check(
            id="decorated_check",
            title="Decorated Check",
            description="A decorated check",
            category=CheckCategory.ENVIRONMENT,
        )
        def my_check(config: DoctorConfig) -> CheckResult:
            return CheckResult(
                id="decorated_check",
                title="Decorated Check",
                category=CheckCategory.ENVIRONMENT,
                status=CheckStatus.PASS,
                message="OK",
            )
        
        registry = get_registry()
        assert "decorated_check" in registry.get_check_ids()
        
        # Verify the function still works
        result = my_check(DoctorConfig())
        assert result.status == CheckStatus.PASS
