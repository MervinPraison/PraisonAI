"""
Tests for Sandbox Executor System.

Test-Driven Development approach for sandboxed execution.
"""

import tempfile

from praisonai.cli.features.sandbox_executor import (
    SandboxMode,
    SandboxPolicy,
    ExecutionResult,
    CommandValidator,
    SubprocessSandbox,
    SandboxExecutorHandler,
)


# ============================================================================
# SandboxMode Tests
# ============================================================================

class TestSandboxMode:
    """Tests for SandboxMode enum."""
    
    def test_mode_values(self):
        """Test mode enum values."""
        assert SandboxMode.DISABLED.value == "disabled"
        assert SandboxMode.BASIC.value == "basic"
        assert SandboxMode.STRICT.value == "strict"
        assert SandboxMode.NETWORK_ISOLATED.value == "network_isolated"
    
    def test_from_string_valid(self):
        """Test parsing valid mode strings."""
        assert SandboxMode.from_string("disabled") == SandboxMode.DISABLED
        assert SandboxMode.from_string("basic") == SandboxMode.BASIC
        assert SandboxMode.from_string("strict") == SandboxMode.STRICT
    
    def test_from_string_with_hyphen(self):
        """Test parsing mode strings with hyphens."""
        assert SandboxMode.from_string("network-isolated") == SandboxMode.NETWORK_ISOLATED
    
    def test_from_string_case_insensitive(self):
        """Test case insensitive parsing."""
        assert SandboxMode.from_string("BASIC") == SandboxMode.BASIC
        assert SandboxMode.from_string("Strict") == SandboxMode.STRICT


# ============================================================================
# SandboxPolicy Tests
# ============================================================================

class TestSandboxPolicy:
    """Tests for SandboxPolicy."""
    
    def test_default_policy(self):
        """Test default policy."""
        policy = SandboxPolicy()
        
        assert policy.mode == SandboxMode.DISABLED
        assert policy.max_memory_mb == 512
        assert policy.allow_network is True
    
    def test_for_mode_disabled(self):
        """Test policy for disabled mode."""
        policy = SandboxPolicy.for_mode(SandboxMode.DISABLED)
        
        assert policy.mode == SandboxMode.DISABLED
    
    def test_for_mode_basic(self):
        """Test policy for basic mode."""
        policy = SandboxPolicy.for_mode(SandboxMode.BASIC)
        
        assert policy.mode == SandboxMode.BASIC
        assert policy.allow_network is True
    
    def test_for_mode_strict(self):
        """Test policy for strict mode."""
        policy = SandboxPolicy.for_mode(SandboxMode.STRICT)
        
        assert policy.mode == SandboxMode.STRICT
        assert policy.max_memory_mb == 256
        assert "curl" in policy.blocked_commands
    
    def test_for_mode_network_isolated(self):
        """Test policy for network isolated mode."""
        policy = SandboxPolicy.for_mode(SandboxMode.NETWORK_ISOLATED)
        
        assert policy.mode == SandboxMode.NETWORK_ISOLATED
        assert policy.allow_network is False


# ============================================================================
# ExecutionResult Tests
# ============================================================================

class TestExecutionResult:
    """Tests for ExecutionResult."""
    
    def test_create_result(self):
        """Test creating execution result."""
        result = ExecutionResult(
            success=True,
            exit_code=0,
            stdout="output",
            stderr="",
            duration_ms=100.0,
            was_sandboxed=True
        )
        
        assert result.success is True
        assert result.exit_code == 0
        assert result.stdout == "output"
    
    def test_output_property(self):
        """Test output property."""
        result = ExecutionResult(
            success=True,
            exit_code=0,
            stdout="out",
            stderr="err",
            duration_ms=100.0,
            was_sandboxed=True
        )
        
        assert result.output == "outerr"
    
    def test_policy_violations(self):
        """Test policy violations."""
        result = ExecutionResult(
            success=False,
            exit_code=-1,
            stdout="",
            stderr="blocked",
            duration_ms=0.0,
            was_sandboxed=True,
            policy_violations=["Command blocked"]
        )
        
        assert len(result.policy_violations) == 1


# ============================================================================
# CommandValidator Tests
# ============================================================================

class TestCommandValidator:
    """Tests for CommandValidator."""
    
    def test_validate_disabled_mode(self):
        """Test validation in disabled mode."""
        policy = SandboxPolicy(mode=SandboxMode.DISABLED)
        validator = CommandValidator(policy)
        
        violations = validator.validate("rm -rf /")
        
        assert len(violations) == 0  # No validation in disabled mode
    
    def test_validate_blocked_command(self):
        """Test validation of blocked command."""
        policy = SandboxPolicy(
            mode=SandboxMode.BASIC,
            blocked_commands={"rm", "sudo"}
        )
        validator = CommandValidator(policy)
        
        violations = validator.validate("rm file.txt")
        
        assert len(violations) > 0
        assert "rm" in violations[0]
    
    def test_validate_dangerous_pattern(self):
        """Test validation of dangerous patterns."""
        policy = SandboxPolicy(mode=SandboxMode.BASIC)
        validator = CommandValidator(policy)
        
        violations = validator.validate("echo test | sh")
        
        assert len(violations) > 0
    
    def test_validate_blocked_path(self):
        """Test validation of blocked paths."""
        policy = SandboxPolicy(
            mode=SandboxMode.BASIC,
            blocked_paths={"/etc", "/var"}
        )
        validator = CommandValidator(policy)
        
        violations = validator.validate("cat /etc/passwd")
        
        assert len(violations) > 0
    
    def test_is_allowed(self):
        """Test is_allowed method."""
        policy = SandboxPolicy(
            mode=SandboxMode.BASIC,
            blocked_commands={"rm"}
        )
        validator = CommandValidator(policy)
        
        assert validator.is_allowed("ls -la") is True
        assert validator.is_allowed("rm file.txt") is False


# ============================================================================
# SubprocessSandbox Tests
# ============================================================================

class TestSubprocessSandbox:
    """Tests for SubprocessSandbox."""
    
    def test_create_sandbox(self):
        """Test creating sandbox."""
        sandbox = SubprocessSandbox()
        assert sandbox is not None
    
    def test_execute_disabled_mode(self):
        """Test execution in disabled mode."""
        policy = SandboxPolicy(mode=SandboxMode.DISABLED)
        sandbox = SubprocessSandbox(policy=policy)
        
        result = sandbox.execute("echo hello")
        
        assert result.success is True
        assert "hello" in result.stdout
        assert result.was_sandboxed is False
    
    def test_execute_basic_mode(self):
        """Test execution in basic mode."""
        policy = SandboxPolicy.for_mode(SandboxMode.BASIC)
        sandbox = SubprocessSandbox(policy=policy)
        
        result = sandbox.execute("echo hello")
        
        assert result.success is True
        assert "hello" in result.stdout
        assert result.was_sandboxed is True
    
    def test_execute_blocked_command(self):
        """Test execution of blocked command."""
        policy = SandboxPolicy(
            mode=SandboxMode.BASIC,
            blocked_commands={"rm"}
        )
        sandbox = SubprocessSandbox(policy=policy)
        
        result = sandbox.execute("rm test.txt")
        
        assert result.success is False
        assert len(result.policy_violations) > 0
    
    def test_execute_timeout(self):
        """Test execution timeout."""
        policy = SandboxPolicy(mode=SandboxMode.BASIC)
        sandbox = SubprocessSandbox(policy=policy)
        
        result = sandbox.execute("sleep 10", timeout=0.1)
        
        assert result.success is False
        assert "timed out" in result.stderr.lower()
    
    def test_execute_with_working_dir(self):
        """Test execution with working directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            policy = SandboxPolicy(mode=SandboxMode.BASIC)
            sandbox = SubprocessSandbox(policy=policy, working_dir=tmpdir)
            
            result = sandbox.execute("pwd")
            
            assert result.success is True
            assert tmpdir in result.stdout


# ============================================================================
# SandboxExecutorHandler Tests
# ============================================================================

class TestSandboxExecutorHandler:
    """Tests for SandboxExecutorHandler."""
    
    def test_handler_creation(self):
        """Test handler creation."""
        handler = SandboxExecutorHandler()
        assert handler.feature_name == "sandbox_executor"
        assert handler.is_enabled is False
    
    def test_initialize_disabled(self):
        """Test initializing with disabled mode."""
        handler = SandboxExecutorHandler()
        sandbox = handler.initialize(mode="disabled")
        
        assert sandbox is not None
        assert handler.is_enabled is False
    
    def test_initialize_basic(self):
        """Test initializing with basic mode."""
        handler = SandboxExecutorHandler()
        sandbox = handler.initialize(mode="basic")
        
        assert sandbox is not None
        assert handler.is_enabled is True
    
    def test_execute(self):
        """Test executing command."""
        handler = SandboxExecutorHandler()
        handler.initialize(mode="basic")
        
        result = handler.execute("echo test")
        
        assert result.success is True
        assert "test" in result.stdout
    
    def test_validate_command(self):
        """Test validating command."""
        handler = SandboxExecutorHandler()
        handler.initialize(mode="basic")
        
        violations = handler.validate_command("echo hello")
        assert len(violations) == 0
    
    def test_get_mode(self):
        """Test getting mode."""
        handler = SandboxExecutorHandler()
        
        assert handler.get_mode() == "disabled"
        
        handler.initialize(mode="strict")
        assert handler.get_mode() == "strict"


# ============================================================================
# Integration Tests
# ============================================================================

class TestSandboxIntegration:
    """Integration tests for Sandbox."""
    
    def test_full_workflow_disabled(self):
        """Test full workflow with sandbox disabled."""
        handler = SandboxExecutorHandler()
        handler.initialize(mode="disabled")
        
        # Should execute without sandboxing
        result = handler.execute("echo hello")
        
        assert result.success is True
        assert result.was_sandboxed is False
    
    def test_full_workflow_basic(self):
        """Test full workflow with basic sandbox."""
        handler = SandboxExecutorHandler()
        handler.initialize(mode="basic")
        
        # Safe command should work
        result = handler.execute("echo hello")
        assert result.success is True
        assert result.was_sandboxed is True
        
        # Blocked command should fail
        result = handler.execute("rm -rf /")
        assert result.success is False
        assert len(result.policy_violations) > 0
    
    def test_strict_mode_isolation(self):
        """Test strict mode isolation."""
        handler = SandboxExecutorHandler()
        handler.initialize(mode="strict")
        
        # Should work in isolated environment
        result = handler.execute("echo $HOME")
        
        assert result.success is True
        assert result.was_sandboxed is True
