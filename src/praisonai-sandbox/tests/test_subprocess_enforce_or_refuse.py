"""SubprocessSandbox enforces a SecurityPolicy field or refuses it when built.

`SecurityPolicy.strict()` on a plain subprocess reported COMPLETED for code
that wrote files and opened sockets: allow_network and allow_file_write were
accepted and never applied. execute(language="bash") skipped every check, and
any other language string ran as Python unchecked.
"""
import asyncio

import pytest

from praisonaiagents.sandbox.config import SandboxConfig, SecurityPolicy
from praisonai_sandbox.subprocess import SubprocessSandbox

# A policy a plain subprocess can keep; each test adds one restriction.
OPEN = dict(allow_network=True, allow_file_write=True, allow_subprocess=True,
            blocked_paths=[], blocked_commands=[], blocked_imports=[])


def _sandbox(**fields):
    return SubprocessSandbox(SandboxConfig(security_policy=SecurityPolicy(**{**OPEN, **fields})))


def _execute(sandbox, code, language="python"):
    async def go():
        await sandbox.start()
        try:
            return await sandbox.execute(code, language=language)
        finally:
            await sandbox.stop()
    return asyncio.run(go())


@pytest.mark.parametrize("field", ["allow_network", "allow_file_write"])
def test_a_restriction_the_backend_cannot_keep_is_refused(field):
    with pytest.raises(ValueError, match=field):
        _sandbox(**{field: False})


def test_strict_is_refused_with_a_way_forward():
    with pytest.raises(ValueError) as info:
        SubprocessSandbox(SandboxConfig(security_policy=SecurityPolicy.strict()))
    assert "docker" in str(info.value) and "sandlock" in str(info.value)


def test_a_policy_swapped_in_after_construction_is_refused_too():
    sandbox = _sandbox()
    sandbox.config.security_policy = SecurityPolicy.strict()
    with pytest.raises(ValueError):
        _execute(sandbox, "print(1)")


def test_the_default_sandbox_still_builds_and_runs():
    assert _execute(SubprocessSandbox(), "print(6 * 7)").stdout.strip() == "42"


@pytest.mark.parametrize("fields, script", [
    (dict(allow_subprocess=False), "echo hi"),
    (dict(blocked_commands=["rm -rf"]), "rm -rf ./nothing-here"),
    (dict(allowed_commands=["python3"]), "echo hi"),
    (dict(blocked_paths=["/etc/hosts"]), "cat /etc/hosts"),
])
def test_a_bash_script_gets_the_command_screen(fields, script):
    result = _execute(_sandbox(**fields), script, language="bash")
    assert result.status.value == "failed"
    assert "policy" in (result.error or "").lower() or "blocked" in (result.error or "").lower()


def test_an_ordinary_bash_script_still_runs():
    assert _execute(_sandbox(), "echo hi", language="bash").stdout.strip() == "hi"


def test_another_language_string_is_screened_as_python():
    """Anything but bash runs under the Python interpreter, so it is checked as Python."""
    result = _execute(_sandbox(blocked_imports=["socket"]), "import socket", language="py3")
    assert result.status.value == "failed"


def test_the_error_is_a_valueerror_and_a_praisonai_error():
    from praisonaiagents.errors import PraisonAIError
    from praisonai_sandbox._enforce import UnenforceablePolicyError

    assert issubclass(UnenforceablePolicyError, ValueError)
    assert issubclass(UnenforceablePolicyError, PraisonAIError)
