"""
Unit tests for DockerSandbox SecurityPolicy enforcement.

These tests exercise the host-side, container-independent parts of the Docker
backend: command-level policy validation before dispatch, and output
truncation to max_output_size after communicate(). No Docker container is
started -- the argv decision and the host-side buffer bound are entirely the
package's own, which is what is measured here.

Regression coverage for issue #4302: DockerSandbox accepted a SecurityPolicy
and enforced none of it.
"""

import pytest

try:
    from praisonai_sandbox.docker import DockerSandbox
    from praisonaiagents.sandbox import SandboxConfig, SandboxStatus
    from praisonaiagents.sandbox.config import SecurityPolicy
except ImportError as e:
    pytest.skip(f"Could not import sandbox modules: {e}", allow_module_level=True)


class TestCommandPolicyValidation:
    """DockerSandbox must enforce command-level policy before dispatch."""

    def _sandbox(self, policy: SecurityPolicy) -> DockerSandbox:
        return DockerSandbox(config=SandboxConfig(security_policy=policy))

    def test_blocked_command_is_refused(self):
        policy = SecurityPolicy(blocked_commands=["rm -rf"])
        error = self._sandbox(policy)._validate_command_against_policy(
            ["rm", "-rf", "/tmp/x"], policy
        )
        assert error == "Blocked command pattern: rm -rf"

    def test_allowed_commands_allowlist_evaporation_regression(self):
        """allowed_commands has no container analogue; it must be enforced."""
        policy = SecurityPolicy(allowed_commands=["python"])
        error = self._sandbox(policy)._validate_command_against_policy(
            ["sh", "-c", "echo hi"], policy
        )
        assert error == "Command not in allowlist: sh"

    def test_allowed_command_passes(self):
        policy = SecurityPolicy(allowed_commands=["python"])
        error = self._sandbox(policy)._validate_command_against_policy(
            ["python", "script.py"], policy
        )
        assert error is None

    def test_blocked_path_is_refused(self):
        policy = SecurityPolicy(blocked_paths=["/etc/passwd"])
        error = self._sandbox(policy)._validate_command_against_policy(
            ["cat", "/etc/passwd"], policy
        )
        assert error == "Access to blocked path: /etc/passwd"

    def test_empty_command_is_refused(self):
        policy = SecurityPolicy()
        error = self._sandbox(policy)._validate_command_against_policy([], policy)
        assert error == "Empty command"

    def test_shell_is_permitted_in_container_regardless_of_allow_subprocess(self):
        """Docker always dispatches via `sh -c` inside the container; unlike the
        host-side subprocess backend, allow_subprocess must not refuse it."""
        policy = SecurityPolicy(allow_subprocess=False)
        error = self._sandbox(policy)._validate_command_against_policy(
            ["sh", "-c", "echo ok"], policy
        )
        assert error is None

    def test_path_outside_allowlist_is_refused(self):
        """allowed_paths must be enforced, matching SubprocessSandbox."""
        policy = SecurityPolicy(allowed_paths=["/sandbox"], blocked_paths=[])
        error = self._sandbox(policy)._validate_command_against_policy(
            ["cat", "/etc/hostname"], policy
        )
        assert error == "Path not in allowlist: /etc/hostname"

    def test_path_inside_allowlist_passes(self):
        policy = SecurityPolicy(allowed_paths=["/sandbox"], blocked_paths=[])
        error = self._sandbox(policy)._validate_command_against_policy(
            ["cat", "/sandbox/report.txt"], policy
        )
        assert error is None

    @pytest.mark.asyncio
    async def test_run_command_scans_shell_payload_for_blocked_path(self):
        """shell=True routes through build_argv; the payload must still be scanned."""
        policy = SecurityPolicy(blocked_paths=["/etc/passwd"])
        sandbox = self._sandbox(policy)
        sandbox._is_running = True
        sandbox._temp_dir = "/tmp"  # noqa: S108

        result = await sandbox.run_command("cat /etc/passwd", shell=True)

        assert result.status == SandboxStatus.FAILED
        assert result.error == "Access to blocked path: /etc/passwd"

    @pytest.mark.asyncio
    async def test_run_command_refuses_blocked_command_without_container(self):
        """run_command must fail the policy check before ever calling docker."""
        policy = SecurityPolicy(blocked_commands=["rm -rf"])
        sandbox = self._sandbox(policy)
        sandbox._is_running = True  # skip start() / docker availability
        sandbox._temp_dir = "/tmp"  # noqa: S108 - not touched on the refusal path

        result = await sandbox.run_command("rm -rf /tmp/canary")

        assert result.status == SandboxStatus.FAILED
        assert result.error == "Blocked command pattern: rm -rf"

    @pytest.mark.asyncio
    async def test_run_command_refuses_command_not_in_allowlist(self):
        policy = SecurityPolicy(allowed_commands=["python"])
        sandbox = self._sandbox(policy)
        sandbox._is_running = True
        sandbox._temp_dir = "/tmp"  # noqa: S108

        result = await sandbox.run_command("sh -c 'echo hi'")

        assert result.status == SandboxStatus.FAILED
        assert "not in allowlist" in result.error


class TestOutputTruncation:
    """max_output_size must bound the host-side communicate() buffer."""

    def test_output_over_limit_is_truncated(self):
        policy = SecurityPolicy(max_output_size=100)
        sandbox = DockerSandbox(config=SandboxConfig(security_policy=policy))

        out = sandbox._truncate_output(b"x" * 200)

        assert out.startswith(b"x" * 100)
        assert b"[OUTPUT TRUNCATED]" in out
        assert len(out) <= 100 + len(b"\n[OUTPUT TRUNCATED]")

    def test_output_under_limit_is_untouched(self):
        policy = SecurityPolicy(max_output_size=1000)
        sandbox = DockerSandbox(config=SandboxConfig(security_policy=policy))

        out = sandbox._truncate_output(b"hello")

        assert out == b"hello"
        assert b"[OUTPUT TRUNCATED]" not in out

    def test_zero_limit_disables_truncation(self):
        policy = SecurityPolicy(max_output_size=0)
        sandbox = DockerSandbox(config=SandboxConfig(security_policy=policy))

        out = sandbox._truncate_output(b"x" * 5000)

        assert out == b"x" * 5000
