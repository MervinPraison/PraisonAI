"""
Unit tests for SubprocessSandbox security and environment isolation.

Tests cover:
- SecurityPolicy-based environment isolation 
- Resource limits enforcement via setrlimit
- Cross-platform compatibility (Windows/POSIX)
- Process group termination and timeout handling
- Output size limits and truncation
"""

import asyncio
import os
import sys
import tempfile
import pytest
from unittest.mock import patch, MagicMock, AsyncMock

try:
    from praisonai_sandbox.subprocess import SubprocessSandbox
    from praisonaiagents.sandbox import SandboxConfig, ResourceLimits, SandboxStatus
    from praisonaiagents.sandbox.config import SecurityPolicy
except ImportError as e:
    pytest.skip(f"Could not import sandbox modules: {e}", allow_module_level=True)


class TestEnvironmentIsolation:
    """Tests for SecurityPolicy-based environment isolation."""

    @pytest.mark.asyncio
    async def test_strict_policy_blocks_host_env(self):
        """Strict policy should not inherit host environment variables."""
        config = SandboxConfig(
            env={},
            security_policy=SecurityPolicy.strict()
        )
        sandbox = SubprocessSandbox(config)
        
        # Build environment for a subprocess 
        env = sandbox._build_child_env(SecurityPolicy.strict(), {})
        
        # Should have minimal required vars only 
        assert "PATH" in env
        assert "HOME" in env
        
        # Should NOT have host environment variables
        # (except the ones we explicitly allow for basic function)
        host_vars = set(os.environ.keys())
        child_vars = set(env.keys())
        leaked_vars = host_vars & child_vars - {"PATH", "HOME"}
        
        # Some proxy vars might be allowed if network is enabled
        proxy_vars = {"HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY", "http_proxy", "https_proxy", "no_proxy"}
        leaked_vars = leaked_vars - proxy_vars
        
        assert len(leaked_vars) == 0, f"Host env vars leaked to child: {leaked_vars}"

    @pytest.mark.asyncio  
    async def test_allow_network_passes_proxy_vars(self):
        """When allow_network=True, proxy vars should be passed through."""
        policy = SecurityPolicy(
            allow_network=True,
            allow_file_write=False,
            max_output_size=1024 * 1024
        )
        
        config = SandboxConfig(env={}, security_policy=policy)
        sandbox = SubprocessSandbox(config)
        
        # Set some proxy vars in host environment
        proxy_env = {
            "HTTP_PROXY": "http://proxy.company.com:8080",
            "HTTPS_PROXY": "https://proxy.company.com:8080",
            "NO_PROXY": "localhost,127.0.0.1"
        }
        
        with patch.dict(os.environ, proxy_env):
            env = sandbox._build_child_env(policy, {})
            
            # Proxy vars should be present when network is allowed
            assert env.get("HTTP_PROXY") == "http://proxy.company.com:8080"
            assert env.get("HTTPS_PROXY") == "https://proxy.company.com:8080"
            assert env.get("NO_PROXY") == "localhost,127.0.0.1"

    @pytest.mark.asyncio
    async def test_no_network_blocks_proxy_vars(self):
        """When allow_network=False, proxy vars should be blocked."""
        policy = SecurityPolicy(
            allow_network=False,
            allow_file_write=False,
            max_output_size=1024 * 1024
        )
        
        config = SandboxConfig(env={}, security_policy=policy)
        sandbox = SubprocessSandbox(config)
        
        # Set proxy vars in host environment
        proxy_env = {
            "HTTP_PROXY": "http://proxy.company.com:8080", 
            "HTTPS_PROXY": "https://proxy.company.com:8080"
        }
        
        with patch.dict(os.environ, proxy_env):
            env = sandbox._build_child_env(policy, {})
            
            # Proxy vars should NOT be present when network is blocked
            assert "HTTP_PROXY" not in env
            assert "HTTPS_PROXY" not in env

    @pytest.mark.asyncio
    async def test_explicit_config_env_preserved(self):
        """Environment variables from SandboxConfig.env should always be included."""
        explicit_env = {
            "CUSTOM_VAR": "custom_value",
            "API_KEY": "secret_key"
        }
        
        config = SandboxConfig(
            env=explicit_env,
            security_policy=SecurityPolicy.strict()
        )
        sandbox = SubprocessSandbox(config)
        
        env = sandbox._build_child_env(SecurityPolicy.strict(), {})
        
        # Explicit config env should be preserved
        assert env["CUSTOM_VAR"] == "custom_value"
        assert env["API_KEY"] == "secret_key"

    @pytest.mark.asyncio
    async def test_call_overrides_merge_correctly(self):
        """Per-call env overrides should merge with config env."""
        config_env = {"CONFIG_VAR": "config_value"}
        call_overrides = {"OVERRIDE_VAR": "override_value", "CONFIG_VAR": "overridden"}
        
        config = SandboxConfig(
            env=config_env,
            security_policy=SecurityPolicy.strict()
        )
        sandbox = SubprocessSandbox(config)
        
        env = sandbox._build_child_env(SecurityPolicy.strict(), call_overrides)
        
        # Call overrides should win over config
        assert env["CONFIG_VAR"] == "overridden"
        assert env["OVERRIDE_VAR"] == "override_value"


class TestResourceLimits:
    """Tests for POSIX resource limits enforcement."""

    def test_apply_rlimits_sets_memory_and_file_limits(self):
        """Resource limits should be applied via setrlimit on POSIX systems."""
        if os.name != "posix":
            pytest.skip("Resource limits only supported on POSIX systems")
            
        sandbox = SubprocessSandbox()
        limits = ResourceLimits(
            memory_mb=128,
            timeout_seconds=30,
            max_processes=10,
            max_open_files=50
        )
        
        # Mock the resource module to verify correct calls
        with patch("resource.setrlimit") as mock_setrlimit:
            with patch("resource.RLIMIT_AS", 9, create=True):
                with patch("resource.RLIMIT_NPROC", 7, create=True):
                    with patch("resource.RLIMIT_NOFILE", 8, create=True):
                        sandbox._apply_rlimits(limits)

            mock_setrlimit.assert_any_call(8, (50, 50))

            # RLIMIT_AS is skipped on macOS, where it is unlimited by default
            # and setting it raises "current limit exceeds maximum limit".
            # Everywhere else it carries the memory cap.
            import sys as _sys

            applied = [call.args[0] for call in mock_setrlimit.call_args_list]
            expected_memory = 128 * 1024 * 1024
            if _sys.platform == "darwin":
                assert 9 not in applied, "RLIMIT_AS cannot be set on Darwin"
            else:
                mock_setrlimit.assert_any_call(9, (expected_memory, expected_memory))

            # RLIMIT_NPROC (7) is deliberately NOT set. POSIX scopes it to the
            # real USER ID, not the process tree, so max_processes=10 counts
            # every process the user already has running and the sandbox cannot
            # fork at all -- `echo a | tr a-z A-Z` dies with
            # "sh: fork: Resource temporarily unavailable".
            # Capping a sandbox's process count needs a cgroup or a container.
            assert not any(
                call.args[0] == 7 for call in mock_setrlimit.call_args_list
            ), "RLIMIT_NPROC is per-user; setting it breaks the sandbox entirely"

    def test_apply_rlimits_applies_each_limit_independently(self):
        """One unsupported limit must not silently skip the rest.

        The limits shared a single try/except, so RLIMIT_AS -- which always
        raises on macOS -- swallowed every later setrlimit call. NOFILE was
        never applied on Darwin as a result.
        """
        if os.name != "posix":
            pytest.skip("Resource limits only supported on POSIX systems")

        sandbox = SubprocessSandbox()
        limits = ResourceLimits(memory_mb=128, timeout_seconds=30, max_open_files=50)

        def fail_on_memory(which, _limits):
            if which == 9:
                raise ValueError("current limit exceeds maximum limit")

        with patch("resource.setrlimit", side_effect=fail_on_memory) as mock_setrlimit:
            with patch("resource.RLIMIT_AS", 9, create=True):
                with patch("resource.RLIMIT_NOFILE", 8, create=True):
                    sandbox._apply_rlimits(limits)

            applied = [call.args[0] for call in mock_setrlimit.call_args_list]
            assert 8 in applied, "a failing RLIMIT_AS must not skip RLIMIT_NOFILE"

    def test_apply_rlimits_handles_missing_resource_module(self):
        """Should handle gracefully when resource module is not available."""
        sandbox = SubprocessSandbox()
        limits = ResourceLimits(memory_mb=128, timeout_seconds=30)

        real_import = __import__

        def fake_import(name, *args, **kwargs):
            if name == "resource":
                raise ImportError("no resource")
            return real_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=fake_import):
            with patch("praisonai_sandbox.subprocess.logger") as mock_logger:
                sandbox._apply_rlimits(limits)
                mock_logger.warning.assert_called_once()

    def test_apply_rlimits_windows_warning(self):
        """Should log warning on Windows where resource limits are not supported."""
        sandbox = SubprocessSandbox()
        limits = ResourceLimits(memory_mb=128, timeout_seconds=30)
        
        with patch('os.name', 'nt'):  # Windows
            with patch('praisonai_sandbox.subprocess.logger') as mock_logger:
                sandbox._apply_rlimits(limits)
                mock_logger.warning.assert_called_with(
                    "Resource limits not supported on Windows - sandbox isolation is weaker"
                )


class TestOutputSizeLimit:
    """Tests for output size limiting and truncation."""

    @pytest.mark.asyncio
    async def test_output_truncation_applied(self):
        """Output should be truncated when it exceeds max_output_size."""
        # Create a policy with small output limit for testing
        policy = SecurityPolicy(
            allow_network=False,
            allow_file_write=True,
            max_output_size=100  # Very small for testing
        )
        
        config = SandboxConfig(security_policy=policy)
        sandbox = SubprocessSandbox(config)
        await sandbox.start()
        
        try:
            # Generate output larger than the limit
            large_output_code = 'print("x" * 200)'  # 200 chars, limit is 100
            
            result = await sandbox.execute(large_output_code)
            
            assert result.status == SandboxStatus.COMPLETED
            # Output should be truncated
            assert len(result.stdout) <= 100 + len("\n[OUTPUT TRUNCATED]")
            assert "[OUTPUT TRUNCATED]" in result.stdout
            
        finally:
            await sandbox.stop()

    @pytest.mark.asyncio
    async def test_small_output_not_truncated(self):
        """Small output should not be truncated."""
        policy = SecurityPolicy(
            allow_network=False,
            allow_file_write=True,
            max_output_size=1000
        )
        
        config = SandboxConfig(security_policy=policy)
        sandbox = SubprocessSandbox(config)
        await sandbox.start()
        
        try:
            result = await sandbox.execute('print("Hello, World!")')
            
            assert result.status == SandboxStatus.COMPLETED
            assert "[OUTPUT TRUNCATED]" not in result.stdout
            assert "Hello, World!" in result.stdout
            
        finally:
            await sandbox.stop()


class TestCrossPlatformCompatibility:
    """Tests for Windows/POSIX compatibility."""

    @pytest.mark.asyncio
    async def test_windows_subprocess_creation(self):
        """On Windows, subprocess should be created without POSIX-only options."""
        sandbox = SubprocessSandbox()
        limits = ResourceLimits(timeout_seconds=10)
        
        with patch('os.name', 'nt'):  # Windows
            with patch('asyncio.create_subprocess_exec') as mock_create:
                mock_proc = MagicMock()
                mock_proc.communicate.return_value = (b"output", b"")
                mock_proc.returncode = 0
                mock_create.return_value = mock_proc
                
                await sandbox.start()
                await sandbox.execute('print("test")', limits=limits)
                
                # Verify subprocess was created without POSIX-only options
                call_kwargs = mock_create.call_args[1]
                assert "preexec_fn" not in call_kwargs
                assert "start_new_session" not in call_kwargs

    @pytest.mark.asyncio  
    async def test_posix_subprocess_creation(self):
        """On POSIX systems, subprocess should use security options."""
        sandbox = SubprocessSandbox()
        limits = ResourceLimits(timeout_seconds=10)
        
        with patch('os.name', 'posix'):
            with patch('asyncio.create_subprocess_exec') as mock_create:
                mock_proc = MagicMock()
                mock_proc.communicate.return_value = (b"output", b"")
                mock_proc.returncode = 0
                mock_create.return_value = mock_proc
                
                await sandbox.start()
                await sandbox.execute('print("test")', limits=limits)
                
                # Verify subprocess was created with POSIX security options
                call_kwargs = mock_create.call_args[1]
                assert "preexec_fn" in call_kwargs
                assert call_kwargs["start_new_session"] is True

    @pytest.mark.asyncio
    async def test_timeout_handling_windows(self):
        """Timeout handling should work correctly on Windows."""
        sandbox = SubprocessSandbox()
        
        with patch('os.name', 'nt'):  # Windows
            with patch('asyncio.create_subprocess_exec') as mock_create:
                mock_proc = MagicMock()
                mock_proc.pid = 1234
                mock_proc.communicate = AsyncMock(side_effect=asyncio.TimeoutError())
                mock_proc.wait = AsyncMock(return_value=None)
                mock_proc.kill = MagicMock()
                mock_create.return_value = mock_proc
                
                await sandbox.start()
                result = await sandbox.execute('sleep 60', limits=ResourceLimits(timeout_seconds=1))
                
                # On Windows, should call proc.kill() for timeout
                mock_proc.kill.assert_called()
                assert result.status == SandboxStatus.TIMEOUT

    @pytest.mark.skipif(
        sys.platform == "win32",
        reason="os.killpg is POSIX-only and not available on Windows",
    )
    @pytest.mark.asyncio
    async def test_timeout_handling_posix(self):
        """Timeout handling should use process groups on POSIX."""
        sandbox = SubprocessSandbox()
        
        with patch('os.name', 'posix'):
            with patch('asyncio.create_subprocess_exec') as mock_create:
                with patch('os.killpg') as mock_killpg:
                    with patch('signal.SIGKILL', 9):
                        mock_proc = MagicMock()
                        mock_proc.pid = 1234
                        mock_proc.communicate = AsyncMock(side_effect=asyncio.TimeoutError())
                        mock_proc.wait = AsyncMock(return_value=None)
                        mock_create.return_value = mock_proc
                        
                        await sandbox.start()
                        result = await sandbox.execute('sleep 60', limits=ResourceLimits(timeout_seconds=1))
                        
                        # On POSIX, should use killpg to kill process group
                        mock_killpg.assert_called_with(1234, 9)
                        assert result.status == SandboxStatus.TIMEOUT


class TestSecurityRegressions:
    """Regression tests for security vulnerabilities."""

    @pytest.mark.asyncio
    async def test_no_host_env_leakage_regression(self):
        """Regression: Ensure host environment doesn't leak into sandbox."""
        # Set some sensitive host environment variables (using clearly fake test values)
        sensitive_env = {
            "AWS_SECRET_ACCESS_KEY": "FAKE_AWS_KEY_FOR_TESTING_ONLY",
            "DATABASE_PASSWORD": "FAKE_DB_PASSWORD_FOR_TESTING_ONLY", 
            "API_TOKEN": "FAKE_API_TOKEN_FOR_TESTING_ONLY"
        }
        
        with patch.dict(os.environ, sensitive_env):
            config = SandboxConfig(
                env={},
                security_policy=SecurityPolicy.strict()
            )
            sandbox = SubprocessSandbox(config)
            
            env = sandbox._build_child_env(SecurityPolicy.strict(), {})
            
            # Sensitive vars should not leak
            assert "AWS_SECRET_ACCESS_KEY" not in env
            assert "DATABASE_PASSWORD" not in env 
            assert "API_TOKEN" not in env

    def test_temp_dir_fallback_security(self):
        """Ensure /tmp fallback is documented and appropriate.""" 
        config = SandboxConfig(security_policy=SecurityPolicy.strict())
        sandbox = SubprocessSandbox(config)
        
        # Before start(), _temp_dir is None, should fall back to /tmp
        env = sandbox._build_child_env(SecurityPolicy.strict(), {})
        assert env["HOME"] == "/tmp"
        
        # The fallback is defensive - normally start() sets _temp_dir
        # This test documents that /tmp is an acceptable fallback for HOME

class TestShellPayloadScanning:
    """blocked_paths must still match when the path is inside `sh -c`.

    With shell semantics an argv is ``["sh", "-c", "cat /etc/passwd"]``. A
    policy walk over argv sees one opaque string starting with "cat", so the
    path check silently stopped matching -- literal `cat /etc/passwd` ran.
    """

    def test_a_shell_payload_is_expanded_for_scanning(self):
        from praisonai_sandbox._shell import policy_scan_parts

        assert "/etc/passwd" in policy_scan_parts(["sh", "-c", "cat /etc/passwd"])

    def test_unbalanced_quotes_fall_back_instead_of_raising(self):
        from praisonai_sandbox._shell import policy_scan_parts

        parts = policy_scan_parts(["sh", "-c", "cat /etc/passwd 'oops"])
        assert "/etc/passwd" in parts

    def test_a_quoted_heredoc_body_is_not_scanned_as_a_command(self):
        """A quoted heredoc body is the literal bytes of a file. Scanning it
        rejected any file whose text merely mentioned a blocked pattern."""
        from praisonai_sandbox._shell import strip_heredoc_bodies

        command = "cat > f.txt <<'EOF'\nplease run rm -rf /tmp\nEOF"
        assert "rm -rf" not in strip_heredoc_bodies(command)

    def test_an_unquoted_heredoc_body_is_still_scanned(self):
        """Unquoted heredocs undergo shell expansion, so their contents really
        can execute and must stay in scope."""
        from praisonai_sandbox._shell import strip_heredoc_bodies

        command = "cat > f.txt <<EOF\nrm -rf /tmp\nEOF"
        assert "rm -rf" in strip_heredoc_bodies(command)

    @pytest.mark.asyncio
    async def test_a_blocked_path_inside_sh_c_is_refused(self):
        from praisonai_sandbox import SubprocessSandbox
        from praisonaiagents.sandbox import SandboxConfig, SecurityPolicy

        policy = SecurityPolicy(allow_subprocess=True, blocked_paths=["/etc/passwd"])
        sandbox = SubprocessSandbox(config=SandboxConfig(security_policy=policy))
        await sandbox.start()
        try:
            result = await sandbox.run_command("cat /etc/passwd", shell=True)
            assert result.error, "a blocked path must be refused, not executed"
            assert "root:" not in (result.stdout or ""), "the file was actually read"
        finally:
            await sandbox.stop()
