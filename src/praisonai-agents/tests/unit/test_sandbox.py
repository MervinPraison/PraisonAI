"""
Unit tests for Sandbox protocols and components.
"""

from praisonaiagents.sandbox import (
    SandboxConfig,
    SandboxResult,
    SandboxStatus,
    ResourceLimits,
    SecurityPolicy,
)


class TestResourceLimits:
    """Tests for ResourceLimits."""
    
    def test_default_limits(self):
        """Test default resource limits."""
        limits = ResourceLimits()
        assert limits.memory_mb == 512
        assert limits.cpu_percent == 100
        assert limits.timeout_seconds == 60
        assert limits.network_enabled is False
    
    def test_minimal_limits(self):
        """Test minimal resource limits."""
        limits = ResourceLimits.minimal()
        assert limits.memory_mb == 128
        assert limits.timeout_seconds == 30
        assert limits.network_enabled is False
    
    def test_generous_limits(self):
        """Test generous resource limits."""
        limits = ResourceLimits.generous()
        assert limits.memory_mb == 2048
        assert limits.timeout_seconds == 300
        assert limits.network_enabled is True
    
    def test_to_dict(self):
        """Test limits serialization."""
        limits = ResourceLimits(memory_mb=256, timeout_seconds=30)
        data = limits.to_dict()
        assert data["memory_mb"] == 256
        assert data["timeout_seconds"] == 30
    
    def test_from_dict(self):
        """Test limits deserialization."""
        data = {"memory_mb": 1024, "cpu_percent": 50, "network_enabled": True}
        limits = ResourceLimits.from_dict(data)
        assert limits.memory_mb == 1024
        assert limits.cpu_percent == 50
        assert limits.network_enabled is True


class TestSecurityPolicy:
    """Tests for SecurityPolicy."""
    
    def test_default_policy(self):
        """Test default security policy."""
        policy = SecurityPolicy()
        assert policy.allow_network is False
        assert policy.allow_file_write is True
        assert policy.allow_subprocess is False
    
    def test_strict_policy(self):
        """Test strict security policy."""
        policy = SecurityPolicy.strict()
        assert policy.allow_network is False
        assert policy.allow_file_write is False
        assert policy.allow_subprocess is False
    
    def test_permissive_policy(self):
        """Test permissive security policy."""
        policy = SecurityPolicy.permissive()
        assert policy.allow_network is True
        assert policy.allow_file_write is True
        assert policy.allow_subprocess is True
    
    def test_blocked_paths(self):
        """Test blocked paths in policy."""
        policy = SecurityPolicy()
        assert "/etc/passwd" in policy.blocked_paths
        assert "~/.ssh" in policy.blocked_paths


class TestSandboxResult:
    """Tests for SandboxResult."""
    
    def test_result_creation(self):
        """Test result creation."""
        result = SandboxResult(
            status=SandboxStatus.COMPLETED,
            exit_code=0,
            stdout="Hello, World!",
        )
        assert result.status == SandboxStatus.COMPLETED
        assert result.exit_code == 0
        assert result.stdout == "Hello, World!"
    
    def test_success_property(self):
        """Test success property."""
        result = SandboxResult(status=SandboxStatus.COMPLETED, exit_code=0)
        assert result.success is True
        
        result = SandboxResult(status=SandboxStatus.COMPLETED, exit_code=1)
        assert result.success is False
        
        result = SandboxResult(status=SandboxStatus.TIMEOUT)
        assert result.success is False
    
    def test_output_property(self):
        """Test combined output property."""
        result = SandboxResult(stdout="out", stderr="err")
        output = result.output
        assert "out" in output
        assert "err" in output
    
    def test_to_dict(self):
        """Test result serialization."""
        result = SandboxResult(
            status=SandboxStatus.COMPLETED,
            exit_code=0,
            stdout="test",
        )
        data = result.to_dict()
        assert data["status"] == "completed"
        assert data["exit_code"] == 0
        assert data["stdout"] == "test"
    
    def test_from_dict(self):
        """Test result deserialization."""
        data = {
            "status": "timeout",
            "error": "Timed out",
            "duration_seconds": 60.0,
        }
        result = SandboxResult.from_dict(data)
        assert result.status == SandboxStatus.TIMEOUT
        assert result.error == "Timed out"


class TestSandboxStatus:
    """Tests for SandboxStatus enum."""
    
    def test_status_values(self):
        """Test status values."""
        assert SandboxStatus.PENDING.value == "pending"
        assert SandboxStatus.RUNNING.value == "running"
        assert SandboxStatus.COMPLETED.value == "completed"
        assert SandboxStatus.FAILED.value == "failed"
        assert SandboxStatus.TIMEOUT.value == "timeout"
        assert SandboxStatus.KILLED.value == "killed"


class TestSandboxConfig:
    """Tests for SandboxConfig."""
    
    def test_default_config(self):
        """Test default sandbox configuration."""
        config = SandboxConfig()
        assert config.sandbox_type == "subprocess"
        assert config.auto_cleanup is True
    
    def test_docker_config(self):
        """Test Docker sandbox configuration."""
        config = SandboxConfig.docker("python:3.11")
        assert config.sandbox_type == "docker"
        assert config.image == "python:3.11"
    
    def test_subprocess_config(self):
        """Test subprocess sandbox configuration."""
        config = SandboxConfig.subprocess()
        assert config.sandbox_type == "subprocess"
    
    def test_to_dict_hides_secrets(self):
        """Test that to_dict hides sensitive env vars."""
        config = SandboxConfig(env={"API_KEY": "secret", "NAME": "test"})
        data = config.to_dict()
        assert data["env"]["API_KEY"] == "***"
        assert data["env"]["NAME"] == "test"
