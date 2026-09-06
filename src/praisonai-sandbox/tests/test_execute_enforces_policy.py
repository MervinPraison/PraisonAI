"""SubprocessSandbox.execute() must enforce the security policy.

`run_command()` validated against the policy. `execute()` did not -- and
execute() is the default backend (SandboxConfig.sandbox_type defaults to
"subprocess") and the path SandboxManager.run_code() takes. So the policy was
decorative on the route almost everyone uses:

    SecurityPolicy.strict()  ->  allow_network=False,
                                 blocked_imports=['subprocess','os.system','eval','exec']

    execute(that code)       ->  status=COMPLETED, exit=0
                                 "SUBPROCESS IMPORTED OK"
                                 "NETWORK REACHED"
                                 "PASSWD: ##"

`blocked_imports` in particular was declared in SecurityPolicy, documented,
and serialised by to_dict() -- and read by no code anywhere in the monorepo.

Scope: this enforces blocked_imports and leaves the command policy to
run_command(). It does NOT implement network isolation -- `allow_network=False`
still needs OS-level sandboxing, and code importing a module that is not on the
blocked list can still open a socket. That remains a real gap, not claimed here.

Most cases exercise the validator directly rather than spawning an interpreter:
an earlier draft ran real subprocesses per case and made this file flaky, and
took two pre-existing tests down with it (clean main was stable over 5 runs,
with that draft it was not). One end-to-end case still spawns, and stops the
sandbox afterwards.
"""
import asyncio

import pytest

from praisonaiagents.sandbox.config import SandboxConfig, SecurityPolicy
from praisonai_sandbox.subprocess import SubprocessSandbox


def _validator(policy=None):
    sandbox = SubprocessSandbox(SandboxConfig(
        security_policy=policy or SecurityPolicy.strict()))
    return lambda code, language="python": sandbox._validate_code_against_policy(
        code, language, sandbox.config.security_policy)


class TestBlockedImportsAreDetected:

    def test_a_blocked_import(self):
        assert _validator()("import subprocess\n") is not None

    def test_from_import(self):
        assert _validator()("from subprocess import run\n") is not None

    def test_a_submodule_import(self):
        assert _validator()("import subprocess.run\n") is not None

    def test_an_aliased_import(self):
        assert _validator()("import subprocess as sp\n") is not None

    def test_a_dotted_call(self):
        """'os.system' names the call, not the os module."""
        assert _validator()("import os\nos.system('echo hi')\n") is not None

    def test_a_bare_blocked_name(self):
        assert _validator()("eval('1+1')\n") is not None


class TestAliasesCannotBypass:
    """A blocked dotted call must not be reachable by renaming the import."""

    def test_a_dotted_call_through_an_import_alias(self):
        assert _validator()("import os as x\nx.system('echo hi')\n") is not None

    def test_a_dotted_call_through_a_from_import(self):
        assert _validator()("from os import system\nsystem('echo hi')\n") is not None

    def test_a_dotted_call_through_an_aliased_from_import(self):
        assert _validator()("from os import system as s\ns('echo hi')\n") is not None


class TestNoFalsePositives:

    def test_a_blocked_word_inside_a_string(self):
        """Substring matching would reject this; parsing does not."""
        assert _validator()("print('the word subprocess in a string')\n") is None

    def test_a_blocked_word_in_a_comment(self):
        assert _validator()("# subprocess is mentioned here\nprint('ok')\n") is None

    def test_a_variable_merely_named_like_one(self):
        assert _validator()("subprocess_count = 3\nprint(subprocess_count)\n") is None

    def test_assigning_to_a_blocked_name_is_not_a_use(self):
        """`subprocess = 3` rebinds the spelling; it does not import or call it."""
        assert _validator()("subprocess = 3\nprint(subprocess)\n") is None

    def test_a_parameter_named_like_a_blocked_name(self):
        """A parameter definition is a binding, not a call to the builtin."""
        assert _validator()("def f(eval):\n    return 1\nf(1)\n") is None

    def test_harmless_code(self):
        assert _validator()("print('hello')\n") is None

    def test_unparseable_code_is_left_to_the_interpreter(self):
        """A syntax error should surface as one, not as a policy violation."""
        assert _validator()("def (\n") is None

    def test_a_non_python_language_is_not_parsed_as_python(self):
        assert _validator()("echo subprocess", language="bash") is None


class TestThePolicyIsRespectedBothWays:

    def test_permissive_blocks_nothing(self):
        assert _validator(SecurityPolicy.permissive())("import subprocess\n") is None

    def test_an_empty_blocked_list_blocks_nothing(self):
        policy = SecurityPolicy.permissive()
        policy.blocked_imports = []
        assert _validator(policy)("import subprocess\n") is None


class TestEndToEnd:
    """One real execution, to prove the validator is actually wired in."""

    def test_strict_policy_refuses_to_run_blocked_code(self):
        async def go():
            sandbox = SubprocessSandbox(SandboxConfig(
                security_policy=SecurityPolicy.strict()))
            try:
                return await sandbox.execute("import subprocess\nprint('RAN')\n")
            finally:
                await sandbox.stop()

        result = asyncio.run(go())
        assert result.status.name == "FAILED"
        assert "subprocess" in (result.stderr or "")
        assert "RAN" not in (result.stdout or "")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
