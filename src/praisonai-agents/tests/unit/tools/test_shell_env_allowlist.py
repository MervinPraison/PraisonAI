"""Model-run commands inherit an allowlisted environment, not the operator's.

The scrub was a denylist of secret-looking names (`*_KEY`, `*TOKEN*`, ...), so
DATABASE_URL with an embedded password, AWS_ACCESS_KEY_ID, a webhook URL or a
GH_PAT reached `env` in a command the model chose. Now only the variables tools
need to start are passed, plus names the operator lists in
PRAISONAI_SHELL_ENV_ALLOWLIST and the caller's explicit env.
"""
import pathlib

import pytest

from praisonaiagents.tools.shell_tools import build_subprocess_env

SECRETS = {
    "DATABASE_URL": "postgres://admin:s3cret@db:5432/app",
    "AWS_ACCESS_KEY_ID": "AKIAEXAMPLE",
    "SLACK_WEBHOOK_URL": "https://hooks.example/T/B/x",
    "GH_PAT": "ghp_example",
    "PGPASSWORD": "pw",
    "SOME_UNKNOWN_SETTING": "x",
}


@pytest.fixture
def host_env(monkeypatch):
    monkeypatch.delenv("PRAISONAI_SHELL_ENV_ALLOWLIST", raising=False)
    for k, v in SECRETS.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setenv("LANG", "en_US.UTF-8")
    monkeypatch.setenv("LC_ALL", "C")


@pytest.mark.parametrize("name", sorted(SECRETS))
def test_an_operator_variable_is_not_inherited(host_env, name):
    assert name not in build_subprocess_env()


@pytest.mark.parametrize("name", ["PATH", "HOME", "LANG", "LC_ALL"])
def test_what_tools_need_to_start_is_kept(host_env, name):
    assert name in build_subprocess_env()


def test_the_operator_can_name_more(host_env, monkeypatch):
    monkeypatch.setenv("PRAISONAI_SHELL_ENV_ALLOWLIST", "DATABASE_URL, GH_PAT")
    env = build_subprocess_env()
    assert env["DATABASE_URL"] == SECRETS["DATABASE_URL"] and env["GH_PAT"] == SECRETS["GH_PAT"]


def test_explicit_env_wins(host_env):
    assert build_subprocess_env({"DATABASE_URL": "sqlite://"})["DATABASE_URL"] == "sqlite://"


def test_every_core_shell_spawn_uses_the_helper():
    """Guard: the shell tool's spawns build env through the shared helper."""
    import praisonaiagents.tools.shell_tools as mod

    source = pathlib.Path(mod.__file__).read_text()
    assert "process_env = _build_subprocess_env(env)" in source
    assert "os.environ.copy()" not in source and "dict(os.environ)" not in source
