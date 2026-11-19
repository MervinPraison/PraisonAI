"""SandlockSandbox must apply every SecurityPolicy field or refuse it.

Landlock bounded the filesystem, but the policy object was barely read: the
network followed ResourceLimits only, allow_file_write was ignored, a caller's
working_dir became a read/write Landlock grant anywhere on the host, and
allow_subprocess, blocked_commands, blocked_imports and max_output_size did
nothing. sandlock is Linux-only, so its module is mocked; the tests check what
SandlockSandbox hands to it and what it refuses before calling it.
"""
import asyncio
import sys
from unittest.mock import MagicMock, Mock, patch

import pytest

from praisonaiagents.sandbox import ResourceLimits, SandboxConfig
from praisonaiagents.sandbox.config import SecurityPolicy


def _fake_sandlock(stdout=b"ok"):
    fake = Mock()
    fake.landlock_abi_version.return_value = 6
    fake.min_landlock_abi.return_value = 6
    result = Mock(success=True, exit_code=0, stdout=stdout, stderr=b"")
    cm = MagicMock()
    cm.__enter__.return_value = Mock(run=Mock(return_value=result))
    fake.Sandbox.return_value = cm
    return fake


def _sandlock(policy, fake=None):
    fake = fake or _fake_sandlock()
    sys.modules.pop("praisonai_sandbox.sandlock", None)
    with patch.dict("sys.modules", {"sandlock": fake}):
        from praisonai_sandbox.sandlock import SandlockSandbox
        sandbox = SandlockSandbox(SandboxConfig(sandbox_type="sandlock", security_policy=policy))
    sandbox._sandlock = fake
    return sandbox, fake


def _run(sandbox, call):
    async def go():
        await sandbox.start()
        try:
            return await call(sandbox)
        finally:
            await sandbox.stop()
    return asyncio.run(go())


def test_the_policy_closes_the_network_even_when_limits_open_it():
    sandbox, _ = _sandlock(SecurityPolicy(allow_network=False))
    assert sandbox._build_sandbox_kwargs(ResourceLimits(network_enabled=True))["net_allow"] == []


def test_allow_file_write_false_grants_no_writable_path(tmp_path):
    sandbox, _ = _sandlock(SecurityPolicy(allow_file_write=False, allowed_paths=[str(tmp_path)]))
    sandbox._temp_dir = str(tmp_path)
    assert sandbox._build_sandbox_kwargs(ResourceLimits(), str(tmp_path))["fs_writable"] == []


def test_allowed_paths_are_readable(tmp_path):
    sandbox, _ = _sandlock(SecurityPolicy(allowed_paths=[str(tmp_path)]))
    assert str(tmp_path) in sandbox._build_sandbox_kwargs(ResourceLimits())["fs_readable"]


def test_a_working_dir_outside_the_sandbox_is_not_granted(tmp_path):
    sandbox, fake = _sandlock(SecurityPolicy(allow_subprocess=True))
    result = _run(sandbox, lambda sb: sb.run_command(["ls"], working_dir=str(tmp_path)))
    assert result.status.value == "failed" and "working_dir" in result.error
    fake.Sandbox.assert_not_called()


def test_a_working_dir_inside_allowed_paths_is_fine(tmp_path):
    sandbox, fake = _sandlock(SecurityPolicy(allow_subprocess=True, allowed_paths=[str(tmp_path)]))
    result = _run(sandbox, lambda sb: sb.run_command(["ls"], working_dir=str(tmp_path)))
    assert result.status.value == "completed"
    assert str(tmp_path) in fake.Sandbox.call_args.kwargs["fs_writable"]


def test_a_blocked_path_inside_an_allowed_path_is_refused_at_construction(tmp_path):
    with pytest.raises(ValueError, match="blocked_paths"):
        _sandlock(SecurityPolicy(allowed_paths=[str(tmp_path)], blocked_paths=[str(tmp_path / "s")]))


@pytest.mark.parametrize("policy, call", [
    (SecurityPolicy(allow_subprocess=False), lambda sb: sb.run_command("id")),
    (SecurityPolicy(allow_subprocess=False), lambda sb: sb.execute("echo hi", language="bash")),
    (SecurityPolicy(allow_subprocess=True, blocked_commands=["rm -rf"]),
     lambda sb: sb.run_command(["rm", "-rf", "x"])),
    (SecurityPolicy(allow_subprocess=True, allowed_commands=["python3"]),
     lambda sb: sb.run_command(["id"])),
    (SecurityPolicy(blocked_imports=["socket"]), lambda sb: sb.execute("import socket")),
])
def test_command_and_import_fields_are_screened(policy, call):
    sandbox, fake = _sandlock(policy)
    result = _run(sandbox, call)
    assert result.status.value == "failed" and "policy" in result.error
    fake.Sandbox.assert_not_called()


def test_max_output_size_truncates():
    sandbox, _ = _sandlock(SecurityPolicy(max_output_size=10), _fake_sandlock(stdout=b"x" * 100))
    result = _run(sandbox, lambda sb: sb.execute("print(1)"))
    assert "[OUTPUT TRUNCATED]" in result.stdout and len(result.stdout) < 40


def test_ordinary_code_still_runs():
    sandbox, fake = _sandlock(SecurityPolicy())
    assert _run(sandbox, lambda sb: sb.execute("print(1)")).status.value == "completed"
    fake.Sandbox.assert_called_once()
