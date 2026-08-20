"""Tests for remaining security hardening (round 2)."""

import os

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


def test_launch_authoriser_parity_single_and_multi_agent():
    """Both launch paths must use the same request authoriser (issue #4083)."""
    from praisonaiagents.agents.agents import _authorise_launch_request as multi
    from praisonaiagents.agent.launch_security import authorise_launch_request as shared
    from praisonaiagents.agent.execution_mixin import ExecutionMixin

    # Multi-agent path re-exports the shared authoriser.
    assert multi is shared
    # Single-agent path imports the same authoriser lazily inside its launcher.
    assert "authorise_launch_request" in ExecutionMixin._launch_http_server.__code__.co_names


def test_launch_wrong_bearer_rejected(monkeypatch):
    from praisonaiagents.agent.launch_security import authorise_launch_request

    monkeypatch.setenv("PRAISONAI_LAUNCH_AUTH_TOKEN", "secret")

    class Wrong:
        headers = {"Authorization": "Bearer nope"}

    class XAuthGood:
        headers = {"X-Auth-Token": "secret"}

    assert authorise_launch_request(Wrong()) is False
    assert authorise_launch_request(XAuthGood()) is True
    monkeypatch.delenv("PRAISONAI_LAUNCH_AUTH_TOKEN", raising=False)


def test_bind_guard_loopback_keyless_allowed(monkeypatch):
    from praisonaiagents.agent.launch_security import resolve_launch_host

    monkeypatch.delenv("PRAISONAI_LAUNCH_AUTH_TOKEN", raising=False)
    # Loopback keyless: unchanged, no token generated (dev flow preserved).
    assert resolve_launch_host("127.0.0.1") == "127.0.0.1"
    assert "PRAISONAI_LAUNCH_AUTH_TOKEN" not in os.environ


def test_bind_guard_non_loopback_keyless_generates_token(monkeypatch, capsys):
    from praisonaiagents.agent.launch_security import resolve_launch_host

    monkeypatch.delenv("PRAISONAI_LAUNCH_AUTH_TOKEN", raising=False)
    host = resolve_launch_host("0.0.0.0")
    # Host still honoured (explicit exposure), but now a token is enforced.
    assert host == "0.0.0.0"
    token = os.environ.get("PRAISONAI_LAUNCH_AUTH_TOKEN")
    assert token
    out = capsys.readouterr().out
    assert token in out
    monkeypatch.delenv("PRAISONAI_LAUNCH_AUTH_TOKEN", raising=False)


def test_bind_guard_preexisting_token_unchanged(monkeypatch):
    from praisonaiagents.agent.launch_security import resolve_launch_host

    monkeypatch.setenv("PRAISONAI_LAUNCH_AUTH_TOKEN", "preset")
    assert resolve_launch_host("0.0.0.0") == "0.0.0.0"
    assert os.environ["PRAISONAI_LAUNCH_AUTH_TOKEN"] == "preset"
    monkeypatch.delenv("PRAISONAI_LAUNCH_AUTH_TOKEN", raising=False)


def test_launch_default_host_is_loopback():
    """Neither launch path should default to binding all interfaces."""
    import inspect
    from praisonaiagents.agent.execution_mixin import ExecutionMixin
    from praisonaiagents.agents.agents import PraisonAIAgents

    assert inspect.signature(ExecutionMixin.launch).parameters["host"].default == "127.0.0.1"
    assert inspect.signature(PraisonAIAgents.launch).parameters["host"].default == "127.0.0.1"


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
