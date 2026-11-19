"""A model-run shell command must not inherit the operator's secrets.

The contained path filtered names matching KEY|TOKEN|SECRET|PASSW|CREDENTIAL,
so DATABASE_URL with a password or AWS_ACCESS_KEY_ID went through; the
uncontained path copied os.environ whole. Both now use the shared allowlist
helper from praisonaiagents.
"""
import sys

import pytest

from praisonai_code.cli.features import shell_exec

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="POSIX shell")


def test_uncontained_shell_does_not_inherit_operator_secrets(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-should-not-leak")
    monkeypatch.setenv("GATEWAY_AUTH_TOKEN", "tok-should-not-leak")
    result = shell_exec._run_real_shell("env", None, 10, None, 100000, contained=False)
    assert "PATH=" in result["stdout"]
    assert "should-not-leak" not in result["stdout"]


def test_the_callers_env_is_still_passed(monkeypatch):
    result = shell_exec._run_real_shell("env", None, 10, {"MY_SETTING": "kept"}, 100000,
                                        contained=False)
    assert "MY_SETTING=kept" in result["stdout"]


def test_the_shared_helper_builds_the_env():
    """Guard: no private copy of the environment in the shell executor."""
    import inspect

    source = inspect.getsource(shell_exec._run_real_shell)
    assert "build_subprocess_env(" in source and "os.environ" not in source
