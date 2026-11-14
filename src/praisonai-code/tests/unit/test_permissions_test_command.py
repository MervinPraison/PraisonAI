"""Tests for ``praisonai permissions test`` (read-only decision explain)."""

import json

from click.testing import CliRunner

from praisonai_code.cli.commands.permissions import permissions


def _run(args):
    return CliRunner().invoke(permissions, args, catch_exceptions=False)


def _decision(args):
    result = _run(["test", *args, "--json"])
    assert result.exit_code == 0, result.output
    return json.loads(result.output)


def test_default_fallthrough_is_ask(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    out = _decision(["bash:ls"])
    assert out["decision"] == "ask"
    assert out["source"] == "default"
    assert out["rule_id"] is None


def test_allow_deny_ask_rules_are_reported(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _run(["allow", "bash:git *"])
    _run(["deny", "bash:rm *"])
    _run(["ask", "write:*"])

    allow = _decision(["bash:git status"])
    assert allow["decision"] == "allow"
    assert allow["source"] == "rule"
    assert allow["pattern"] == "bash:git *"

    # Space after the tool prefix is tolerated; compound commands are split.
    deny = _decision(["bash: git status && rm -rf build"])
    assert deny["target"] == "bash:git status && rm -rf build"
    assert deny["decision"] == "deny"

    ask = _decision(["write:notes.txt"])
    assert ask["decision"] == "ask"
    assert ask["source"] == "rule"


def test_test_command_does_not_persist_anything(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _run(["test", "bash:ls"])
    assert not (tmp_path / ".praisonai").exists()


def test_compound_allow_reports_sub_operations(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _run(["allow", "bash:git *"])
    out = _decision(["bash:git status && git diff"])
    assert out["decision"] == "allow"
    assert out["source"] == "sub-operations"


def test_file_argument_whitespace_is_preserved(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _run(["deny", "write: notes.txt"])
    _run(["allow", "write:*"])
    out = _decision(["write: notes.txt"])
    assert out["target"] == "write: notes.txt"
    assert out["decision"] == "deny"


def test_text_output(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _run(["deny", "bash:sudo *"])
    result = _run(["test", "bash:sudo reboot"])
    assert result.exit_code == 0
    assert "deny" in result.output
    assert "bash:sudo *" in result.output
