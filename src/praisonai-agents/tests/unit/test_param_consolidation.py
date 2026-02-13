"""
TDD tests for Agent parameter consolidation.

Tests:
1. Deprecation warnings fire for old params
2. New config fields work (ExecutionConfig.code_execution, MemoryConfig.auto_save, AutonomyConfig.verification_hooks)
3. Backward compatibility: old params still function correctly
4. Config fields take precedence over deprecated standalone params
"""

import warnings
import pytest


class TestDeprecationWarnings:
    """Test that deprecated params emit DeprecationWarning."""

    def test_allow_delegation_warns(self):
        """allow_delegation=True should emit DeprecationWarning."""
        from praisonaiagents import Agent
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            agent = Agent(name="test", instructions="test", allow_delegation=True)
            deprecation_warnings = [x for x in w if issubclass(x.category, DeprecationWarning)]
            msgs = [str(x.message) for x in deprecation_warnings]
            assert any("allow_delegation" in m for m in msgs), f"Expected allow_delegation deprecation, got: {msgs}"

    def test_allow_code_execution_warns(self):
        """allow_code_execution=True should emit DeprecationWarning."""
        from praisonaiagents import Agent
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            agent = Agent(name="test", instructions="test", allow_code_execution=True)
            deprecation_warnings = [x for x in w if issubclass(x.category, DeprecationWarning)]
            msgs = [str(x.message) for x in deprecation_warnings]
            assert any("allow_code_execution" in m for m in msgs), f"Expected allow_code_execution deprecation, got: {msgs}"

    def test_code_execution_mode_unsafe_warns(self):
        """code_execution_mode='unsafe' should emit DeprecationWarning."""
        from praisonaiagents import Agent
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            agent = Agent(name="test", instructions="test", code_execution_mode="unsafe")
            deprecation_warnings = [x for x in w if issubclass(x.category, DeprecationWarning)]
            msgs = [str(x.message) for x in deprecation_warnings]
            assert any("code_execution_mode" in m for m in msgs), f"Expected code_execution_mode deprecation, got: {msgs}"

    def test_code_execution_mode_safe_no_warn(self):
        """code_execution_mode='safe' (default) should NOT emit DeprecationWarning."""
        from praisonaiagents import Agent
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            agent = Agent(name="test", instructions="test", code_execution_mode="safe")
            deprecation_warnings = [x for x in w if issubclass(x.category, DeprecationWarning)]
            msgs = [str(x.message) for x in deprecation_warnings]
            assert not any("code_execution_mode" in m for m in msgs), f"Unexpected code_execution_mode deprecation for default 'safe'"

    def test_auto_save_warns(self):
        """auto_save='session' should emit DeprecationWarning."""
        from praisonaiagents import Agent
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            agent = Agent(name="test", instructions="test", auto_save="my_session")
            deprecation_warnings = [x for x in w if issubclass(x.category, DeprecationWarning)]
            msgs = [str(x.message) for x in deprecation_warnings]
            assert any("auto_save" in m for m in msgs), f"Expected auto_save deprecation, got: {msgs}"

    def test_rate_limiter_warns(self):
        """rate_limiter=obj should emit DeprecationWarning."""
        from praisonaiagents import Agent

        class FakeLimiter:
            def acquire(self): pass

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            agent = Agent(name="test", instructions="test", rate_limiter=FakeLimiter())
            deprecation_warnings = [x for x in w if issubclass(x.category, DeprecationWarning)]
            msgs = [str(x.message) for x in deprecation_warnings]
            assert any("rate_limiter" in m for m in msgs), f"Expected rate_limiter deprecation, got: {msgs}"

    def test_verification_hooks_warns(self):
        """verification_hooks=[...] should emit DeprecationWarning."""
        from praisonaiagents import Agent
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            agent = Agent(name="test", instructions="test", verification_hooks=["hook1"])
            deprecation_warnings = [x for x in w if issubclass(x.category, DeprecationWarning)]
            msgs = [str(x.message) for x in deprecation_warnings]
            assert any("verification_hooks" in m for m in msgs), f"Expected verification_hooks deprecation, got: {msgs}"

    def test_no_deprecation_on_clean_usage(self):
        """Clean usage (no deprecated params) should NOT emit DeprecationWarning."""
        from praisonaiagents import Agent
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            agent = Agent(name="test", instructions="test")
            deprecation_warnings = [x for x in w if issubclass(x.category, DeprecationWarning)]
            # Filter out llm= deprecation which is a separate concern
            non_llm = [x for x in deprecation_warnings if "llm" not in str(x.message).lower()]
            assert len(non_llm) == 0, f"Unexpected deprecation warnings: {[str(x.message) for x in non_llm]}"


class TestNewConfigFields:
    """Test new fields on config dataclasses."""

    def test_execution_config_code_execution_field(self):
        """ExecutionConfig should have code_execution field."""
        from praisonaiagents.config.feature_configs import ExecutionConfig
        config = ExecutionConfig(code_execution=True, code_mode="unsafe")
        assert config.code_execution is True
        assert config.code_mode == "unsafe"

    def test_execution_config_rate_limiter_field(self):
        """ExecutionConfig should have rate_limiter field."""
        from praisonaiagents.config.feature_configs import ExecutionConfig

        class FakeLimiter:
            def acquire(self): pass

        limiter = FakeLimiter()
        config = ExecutionConfig(rate_limiter=limiter)
        assert config.rate_limiter is limiter

    def test_execution_config_defaults(self):
        """ExecutionConfig defaults should be safe."""
        from praisonaiagents.config.feature_configs import ExecutionConfig
        config = ExecutionConfig()
        assert config.code_execution is False
        assert config.code_mode == "safe"
        assert config.rate_limiter is None

    def test_execution_config_to_dict(self):
        """ExecutionConfig.to_dict() should include code_execution and code_mode."""
        from praisonaiagents.config.feature_configs import ExecutionConfig
        config = ExecutionConfig(code_execution=True, code_mode="unsafe")
        d = config.to_dict()
        assert d["code_execution"] is True
        assert d["code_mode"] == "unsafe"

    def test_memory_config_auto_save_field(self):
        """MemoryConfig should have auto_save field."""
        from praisonaiagents.config.feature_configs import MemoryConfig
        config = MemoryConfig(auto_save="my_session")
        assert config.auto_save == "my_session"

    def test_memory_config_auto_save_default(self):
        """MemoryConfig.auto_save should default to None."""
        from praisonaiagents.config.feature_configs import MemoryConfig
        config = MemoryConfig()
        assert config.auto_save is None

    def test_memory_config_to_dict_includes_auto_save(self):
        """MemoryConfig.to_dict() should include auto_save."""
        from praisonaiagents.config.feature_configs import MemoryConfig
        config = MemoryConfig(auto_save="bot_session")
        d = config.to_dict()
        assert d["auto_save"] == "bot_session"

    def test_autonomy_config_verification_hooks_field(self):
        """AutonomyConfig should have verification_hooks field."""
        from praisonaiagents.agent.autonomy import AutonomyConfig
        hooks = ["hook1", "hook2"]
        config = AutonomyConfig(verification_hooks=hooks)
        assert config.verification_hooks == hooks

    def test_autonomy_config_verification_hooks_default(self):
        """AutonomyConfig.verification_hooks should default to None."""
        from praisonaiagents.agent.autonomy import AutonomyConfig
        config = AutonomyConfig()
        assert config.verification_hooks is None

    def test_autonomy_config_from_dict_verification_hooks(self):
        """AutonomyConfig.from_dict() should extract verification_hooks."""
        from praisonaiagents.agent.autonomy import AutonomyConfig
        hooks = ["hook_a"]
        config = AutonomyConfig.from_dict({"verification_hooks": hooks})
        assert config.verification_hooks == hooks


class TestConsolidatedExtraction:
    """Test that config fields are extracted into Agent attributes."""

    def test_execution_config_code_execution_sets_attribute(self):
        """Agent(execution=ExecutionConfig(code_execution=True)) should set allow_code_execution."""
        from praisonaiagents import Agent
        from praisonaiagents.config.feature_configs import ExecutionConfig
        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            agent = Agent(
                name="test",
                instructions="test",
                execution=ExecutionConfig(code_execution=True, code_mode="unsafe"),
            )
        assert agent.allow_code_execution is True
        assert agent.code_execution_mode == "unsafe"

    def test_execution_config_rate_limiter_sets_attribute(self):
        """Agent(execution=ExecutionConfig(rate_limiter=obj)) should set _rate_limiter."""
        from praisonaiagents import Agent
        from praisonaiagents.config.feature_configs import ExecutionConfig

        class FakeLimiter:
            def acquire(self): pass

        limiter = FakeLimiter()
        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            agent = Agent(
                name="test",
                instructions="test",
                execution=ExecutionConfig(rate_limiter=limiter),
            )
        assert agent._rate_limiter is limiter

    def test_autonomy_config_verification_hooks_sets_attribute(self):
        """Agent(autonomy=AutonomyConfig(verification_hooks=[...])) should set _verification_hooks."""
        from praisonaiagents import Agent
        from praisonaiagents.agent.autonomy import AutonomyConfig
        hooks = ["hook1"]
        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            agent = Agent(
                name="test",
                instructions="test",
                autonomy=AutonomyConfig(verification_hooks=hooks),
            )
        assert agent._verification_hooks == hooks


class TestBackwardCompatibility:
    """Test that deprecated params still work (no breakage)."""

    def test_allow_delegation_still_stored(self):
        """allow_delegation should still be stored on Agent."""
        from praisonaiagents import Agent
        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            agent = Agent(name="test", instructions="test", allow_delegation=True)
        assert agent.allow_delegation is True

    def test_allow_code_execution_still_stored(self):
        """allow_code_execution should still be stored on Agent."""
        from praisonaiagents import Agent
        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            agent = Agent(name="test", instructions="test", allow_code_execution=True)
        assert agent.allow_code_execution is True

    def test_auto_save_still_stored(self):
        """auto_save should still be stored on Agent."""
        from praisonaiagents import Agent
        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            agent = Agent(name="test", instructions="test", auto_save="session1")
        assert agent.auto_save == "session1"

    def test_rate_limiter_still_stored(self):
        """rate_limiter should still be stored on Agent."""
        from praisonaiagents import Agent

        class FakeLimiter:
            def acquire(self): pass

        limiter = FakeLimiter()
        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            agent = Agent(name="test", instructions="test", rate_limiter=limiter)
        assert agent._rate_limiter is limiter

    def test_verification_hooks_still_stored(self):
        """verification_hooks should still be stored on Agent."""
        from praisonaiagents import Agent
        hooks = ["hook1"]
        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            agent = Agent(name="test", instructions="test", verification_hooks=hooks)
        assert agent._verification_hooks == hooks


class TestConfigPrecedence:
    """Test that config fields take precedence over deprecated standalone params."""

    def test_execution_config_overrides_standalone_code_execution(self):
        """ExecutionConfig.code_execution should override standalone allow_code_execution."""
        from praisonaiagents import Agent
        from praisonaiagents.config.feature_configs import ExecutionConfig
        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            agent = Agent(
                name="test",
                instructions="test",
                allow_code_execution=False,  # deprecated standalone
                execution=ExecutionConfig(code_execution=True),  # config takes precedence
            )
        assert agent.allow_code_execution is True

    def test_execution_config_overrides_standalone_rate_limiter(self):
        """ExecutionConfig.rate_limiter should override standalone rate_limiter."""
        from praisonaiagents import Agent
        from praisonaiagents.config.feature_configs import ExecutionConfig

        class Limiter1:
            def acquire(self): pass

        class Limiter2:
            def acquire(self): pass

        old_limiter = Limiter1()
        new_limiter = Limiter2()
        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            agent = Agent(
                name="test",
                instructions="test",
                rate_limiter=old_limiter,  # deprecated standalone
                execution=ExecutionConfig(rate_limiter=new_limiter),  # config takes precedence
            )
        assert agent._rate_limiter is new_limiter
