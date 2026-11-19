"""SandboxExecutor applies each SandboxPolicy field, or refuses/warns about it.

NETWORK_ISOLATED set allow_network=False and nothing read it, so that mode
filtered exactly like BASIC. The resource limits, temp_dir and allowed_paths
were stored and never applied, and the path check split the command differently
from how it was executed and skipped relative paths.
"""
import logging
import os
import sys

import pytest

from praisonai_code.cli.features.sandbox_executor import (
    CommandValidator, SandboxMode, SandboxPolicy, SubprocessSandbox,
)


def _violations(mode, command, cwd=None, **fields):
    policy = SandboxPolicy.for_mode(mode)
    for key, value in fields.items():
        setattr(policy, key, value)
    return CommandValidator(policy).validate(command, cwd)


@pytest.mark.parametrize("command", ["curl https://example.com", "wget x", "nc host 80",
                                     "python3 -c 'print(1)'", "ssh host"])
def test_network_isolated_refuses_network_commands(command):
    assert _violations(SandboxMode.NETWORK_ISOLATED, command)
    assert not _violations(SandboxMode.BASIC, command)


def test_a_relative_climb_into_a_blocked_path_is_refused(tmp_path):
    work = tmp_path / "a" / "b"
    work.mkdir(parents=True)
    climb = "../" * len(work.parts) + "etc/hostname"
    assert _violations(SandboxMode.STRICT, f"cat {climb}", cwd=str(work))


def test_a_quoted_absolute_path_is_checked():
    assert _violations(SandboxMode.STRICT, "cat '/etc/hostname'")


def test_a_relative_path_inside_the_working_dir_is_fine(tmp_path):
    assert not _violations(SandboxMode.STRICT, "cat notes.txt", cwd=str(tmp_path))


def test_allowed_paths_is_applied(tmp_path):
    outside = tmp_path / "outside"
    assert _violations(SandboxMode.BASIC, f"cat {outside}/f", cwd=str(tmp_path / "w"),
                       allowed_paths={str(tmp_path / "w")}, blocked_paths=set())


def test_allowed_hosts_cannot_be_enforced_so_it_is_refused():
    policy = SandboxPolicy.for_mode(SandboxMode.BASIC)
    policy.allowed_hosts = {"example.com"}
    with pytest.raises(ValueError, match="allowed_hosts"):
        SubprocessSandbox(policy=policy)


def test_max_processes_warns_that_it_is_not_enforced(caplog):
    with caplog.at_level(logging.WARNING):
        SubprocessSandbox(policy=SandboxPolicy.for_mode(SandboxMode.STRICT))
    assert "max_processes" in caplog.text


def test_temp_dir_is_used_for_strict_mode(tmp_path):
    policy = SandboxPolicy.for_mode(SandboxMode.STRICT)
    policy.temp_dir = str(tmp_path)
    sandbox = SubprocessSandbox(policy=policy)
    assert sandbox._setup_temp_dir().parent == tmp_path
    sandbox._cleanup_temp_dir()


@pytest.mark.skipif(os.name != "posix", reason="POSIX resource limits")
def test_file_size_limit_is_applied(tmp_path):
    policy = SandboxPolicy.for_mode(SandboxMode.BASIC)
    policy.max_file_size_mb = 1
    policy.blocked_paths = set()  # the interpreter may live under /home or /usr
    sandbox = SubprocessSandbox(policy=policy, working_dir=str(tmp_path))
    result = sandbox.execute(
        f"{sys.executable} -c \"open('big.bin', 'wb').write(bytes(3 * 1024 * 1024))\"")
    assert not result.success
    assert (tmp_path / "big.bin").stat().st_size <= 1024 * 1024
