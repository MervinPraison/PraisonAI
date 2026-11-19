"""Guard: for each local backend x each SecurityPolicy field, the field is either
enforced (proved here) or refused when the sandbox is built. A new
SecurityPolicy field fails this guard until it is classified for every backend.
"""
import asyncio
import dataclasses
import sys
from unittest.mock import MagicMock, Mock, patch

import pytest

from praisonaiagents.sandbox import ResourceLimits, SandboxConfig
from praisonaiagents.sandbox.config import SecurityPolicy

OPEN = dict(allow_network=True, allow_file_write=True, allow_subprocess=True,
            blocked_paths=[], blocked_commands=[], blocked_imports=[])


def _subprocess(**fields):
    from praisonai_sandbox.subprocess import SubprocessSandbox

    return SubprocessSandbox(SandboxConfig(security_policy=SecurityPolicy(**{**OPEN, **fields})))


def _sandlock(**fields):
    fake = Mock(**{"landlock_abi_version.return_value": 6, "min_landlock_abi.return_value": 6})
    cm = MagicMock()
    cm.__enter__.return_value = Mock(run=Mock(return_value=Mock(
        success=True, exit_code=0, stdout=b"x" * 100, stderr=b"")))
    fake.Sandbox.return_value = cm
    sys.modules.pop("praisonai_sandbox.sandlock", None)
    with patch.dict("sys.modules", {"sandlock": fake}):
        from praisonai_sandbox.sandlock import SandlockSandbox
        sandbox = SandlockSandbox(SandboxConfig(security_policy=SecurityPolicy(**{**OPEN, **fields})))
    sandbox._sandlock = fake
    return sandbox


def _run(sandbox, call):
    async def go():
        await sandbox.start()
        try:
            return await call(sandbox)
        finally:
            await sandbox.stop()
    return asyncio.run(go())


def _refused(make, **fields):
    with pytest.raises(ValueError):
        make(**fields)
    return True


def _failed(make, call, **fields):
    return _run(make(**fields), call).status.value == "failed"


BASH = lambda script: (lambda sb: sb.execute(script, language="bash"))  # noqa: E731
PY = lambda code: (lambda sb: sb.execute(code))  # noqa: E731
KWARGS = lambda sb, **kw: sb._build_sandbox_kwargs(ResourceLimits(**kw), sb._temp_dir)  # noqa: E731


def _sandlock_kwargs(field_value, **limits):
    sandbox = _sandlock(**field_value)
    sandbox._temp_dir = "/nonexistent-sandbox-root"
    return KWARGS(sandbox, **limits)


ENFORCED = {
    "subprocess": {
        "allow_network": lambda m: _refused(m, allow_network=False),
        "allow_file_write": lambda m: _refused(m, allow_file_write=False),
        "allow_subprocess": lambda m: _failed(m, BASH("echo hi"), allow_subprocess=False),
        "allowed_paths": lambda m: _failed(m, PY("open('/etc/hosts')"), allowed_paths=["/nonexistent"]),
        "blocked_paths": lambda m: _failed(m, BASH("cat /etc/hosts"), blocked_paths=["/etc/hosts"]),
        "allowed_commands": lambda m: _failed(m, BASH("echo hi"), allowed_commands=["python3"]),
        "blocked_commands": lambda m: _failed(m, BASH("rm -rf ./x"), blocked_commands=["rm -rf"]),
        "allowed_imports": lambda m: _failed(m, PY("import socket"), allowed_imports=["json"]),
        "blocked_imports": lambda m: _failed(m, PY("import socket"), blocked_imports=["socket"]),
        "max_output_size": lambda m: "TRUNCATED" in _run(
            m(max_output_size=10), PY("print('x' * 100)")).stdout,
    },
    "sandlock": {
        "allow_network": lambda m: _sandlock_kwargs(
            dict(allow_network=False), network_enabled=True)["net_allow"] == [],
        "allow_file_write": lambda m: _sandlock_kwargs(dict(allow_file_write=False))["fs_writable"] == [],
        "allow_subprocess": lambda m: _failed(m, BASH("echo hi"), allow_subprocess=False),
        "allowed_paths": lambda m: _failed(
            m, lambda sb: sb.run_command(["ls"], working_dir="/etc"), allowed_paths=["/nonexistent"]),
        "blocked_paths": lambda m: _failed(m, BASH("cat /etc/hosts"), blocked_paths=["/etc/hosts"]),
        "allowed_commands": lambda m: _failed(m, BASH("echo hi"), allowed_commands=["python3"]),
        "blocked_commands": lambda m: _failed(m, BASH("rm -rf ./x"), blocked_commands=["rm -rf"]),
        "allowed_imports": lambda m: _failed(m, PY("import socket"), allowed_imports=["json"]),
        "blocked_imports": lambda m: _failed(m, PY("import socket"), blocked_imports=["socket"]),
        "max_output_size": lambda m: "TRUNCATED" in _run(m(max_output_size=10), PY("print(1)")).stdout,
    },
}
MAKERS = {"subprocess": _subprocess, "sandlock": _sandlock}


@pytest.mark.parametrize("backend", sorted(ENFORCED))
def test_every_field_is_classified(backend):
    fields = {f.name for f in dataclasses.fields(SecurityPolicy)}
    assert fields == set(ENFORCED[backend]), "classify the new SecurityPolicy field for every backend"


@pytest.mark.parametrize("backend, field", [(b, f) for b in sorted(ENFORCED) for f in sorted(ENFORCED[b])])
def test_field_is_enforced_or_refused(backend, field):
    assert ENFORCED[backend][field](MAKERS[backend])
