"""Tests for remaining security hardening (round 2)."""

import pytest


def test_launch_auth_optional_by_default():
    from praisonaiagents.agents.agents import _authorise_launch_request

    class Req:
        headers = {}

    assert _authorise_launch_request(Req()) is True


def test_launch_auth_enforced_when_token_set(monkeypatch):
    from praisonaiagents.agents.agents import _authorise_launch_request

    monkeypatch.setenv("PRAISONAI_LAUNCH_AUTH_TOKEN", "secret")

    class Bad:
        headers = {}

    class Good:
        headers = {"Authorization": "Bearer secret"}

    assert _authorise_launch_request(Bad()) is False
    assert _authorise_launch_request(Good()) is True

    monkeypatch.delenv("PRAISONAI_LAUNCH_AUTH_TOKEN", raising=False)


def test_mentions_reject_outside_workspace(tmp_path):
    from praisonaiagents.tools.mentions import MentionsParser

    outside = tmp_path / "secret.txt"
    outside.write_text("secret", encoding="utf-8")
    ws = tmp_path / "ws"
    ws.mkdir()
    parser = MentionsParser(workspace_path=str(ws))
    context, _ = parser.process(f"@file:{outside}")
    assert "outside workspace" in context.lower() or "not allowed" in context.lower()


def test_imap_sanitize_rejects_injection():
    from praisonaiagents.tools.email_tools import _imap_sanitize

    with pytest.raises(ValueError):
        _imap_sanitize('test"\r\nBAD')
