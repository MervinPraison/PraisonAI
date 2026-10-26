"""Shell tool must not hand parent-process secrets to model-driven commands (#5986)."""

import sys
import time

import pytest

from praisonaiagents.tools import shell_tools
from praisonaiagents.tools.shell_tools import ShellTools, _build_subprocess_env, _expandvars, _is_secret_name

posix = pytest.mark.skipif(sys.platform == "win32", reason="POSIX commands")


@pytest.fixture(autouse=True)
def _auto_approve(monkeypatch):
    monkeypatch.setenv("PRAISONAI_AUTO_APPROVE", "true")


def _run(command, **kwargs):
    return ShellTools().execute_command(command, **kwargs)


def test_secret_names_detected():
    for name in ("OPENAI_API_KEY", "GATEWAY_AUTH_TOKEN", "AWS_SECRET_ACCESS_KEY", "DB_PASSWORD", "GH_TOKEN"):
        assert _is_secret_name(name), name
    for name in ("PATH", "HOME", "LANG", "VIRTUAL_ENV", "SSH_AUTH_SOCK", "TMPDIR"):
        assert not _is_secret_name(name), name


def test_secrets_stripped_operational_vars_kept(monkeypatch):
    monkeypatch.setenv("GATEWAY_AUTH_TOKEN", "gw-secret")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-secret")
    env = _build_subprocess_env()
    assert "GATEWAY_AUTH_TOKEN" not in env
    assert "OPENAI_API_KEY" not in env
    assert "PATH" in env


@posix
def test_env_command_does_not_leak(monkeypatch):
    monkeypatch.setenv("GATEWAY_AUTH_TOKEN", "gw-secret-value")
    result = _run("env")
    assert result["success"]
    assert "gw-secret-value" not in result["stdout"]


@posix
def test_argument_expansion_does_not_leak(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-secret-value")
    monkeypatch.setenv("PLAIN_VAR", "visible")
    result = _run("echo $OPENAI_API_KEY ${PLAIN_VAR}")
    assert "sk-secret-value" not in result["stdout"]
    assert "visible" in result["stdout"]


def test_explicit_env_and_allowlist_pass_through(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "allowed-value")
    monkeypatch.setenv("PRAISONAI_SHELL_ENV_ALLOWLIST", "GITHUB_TOKEN")
    env = _build_subprocess_env({"MY_TOKEN": "explicit"})
    assert env["GITHUB_TOKEN"] == "allowed-value"
    assert env["MY_TOKEN"] == "explicit"


@posix
def test_background_command_does_not_leak(monkeypatch):
    monkeypatch.setenv("GATEWAY_AUTH_TOKEN", "bg-secret-value")
    tools = ShellTools()
    started = tools.execute_command("env", run_in_background=True)
    assert started["success"]
    tools._background[started["process_id"]]["process"].wait(timeout=10)
    time.sleep(0.1)
    with open(started["log_file"]) as fh:
        output = fh.read()
    assert "PATH=" in output
    assert "bg-secret-value" not in output


@posix
def test_cwd_expansion_uses_scrubbed_env(monkeypatch, tmp_path):
    monkeypatch.setenv("SERVICE_TOKEN", str(tmp_path))
    assert _run("pwd", cwd="$WORK_DIR", env={"WORK_DIR": str(tmp_path)})["stdout"].strip() == str(tmp_path)
    assert _run("pwd", cwd="$SERVICE_TOKEN")["stdout"].strip() != str(tmp_path)


def test_windows_percent_expansion(monkeypatch):
    monkeypatch.setattr(shell_tools.platform, "system", lambda: "Windows")
    env = {"USERPROFILE": r"C:\Users\me"}
    assert _expandvars(r"%userprofile%\project", env) == r"C:\Users\me\project"
    assert _expandvars("%OPENAI_API_KEY%", env) == "%OPENAI_API_KEY%"
    assert _expandvars("50%", env) == "50%"
