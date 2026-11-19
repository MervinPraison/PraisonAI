"""Operator credentials go only to the operator's server.

A tool URL argument is chosen by the model and a fetched OpenAPI spec is
remote content; neither may decide where an operator-held token is sent.
No test reaches the network.
"""
from __future__ import annotations

import sys
import types
import warnings

import pytest


@pytest.fixture
def fake_jira(monkeypatch):
    """A stand-in ``jira`` module that records where credentials were sent."""
    sent = []

    class JIRA:
        def __init__(self, server, basic_auth):
            sent.append((server, basic_auth))

    monkeypatch.setitem(sys.modules, "jira", types.SimpleNamespace(JIRA=JIRA))
    for name in ("JIRA_URL", "JIRA_USERNAME"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("JIRA_EMAIL", "owner@corp.example")
    monkeypatch.setenv("JIRA_API_TOKEN", "OPERATOR-TOKEN")
    return sent


def _connect():
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        from praisonaiagents.tools.jira_tools import _get_jira_connection
    return _get_jira_connection


def test_env_token_not_sent_to_model_chosen_server(fake_jira, monkeypatch):
    monkeypatch.setenv("JIRA_URL", "https://corp.atlassian.net")
    with pytest.raises(ValueError, match="JIRA_URL"):
        _connect()("https://foreign.invalid")
    assert fake_jira == []


def test_env_token_needs_jira_url(fake_jira):
    with pytest.raises(ValueError, match="JIRA_URL"):
        _connect()("https://foreign.invalid")
    assert fake_jira == []


def test_env_token_sent_to_jira_url(fake_jira, monkeypatch):
    monkeypatch.setenv("JIRA_URL", "https://corp.atlassian.net")
    _connect()("https://CORP.atlassian.net/")
    _connect()("")
    assert [s for s, _ in fake_jira] == ["https://CORP.atlassian.net/", "https://corp.atlassian.net"]
    assert fake_jira[0][1] == ("owner@corp.example", "OPERATOR-TOKEN")


def test_explicit_token_may_name_its_server(fake_jira):
    _connect()("https://other.example", token="CALLER-TOKEN")
    assert fake_jira == [("https://other.example", ("owner@corp.example", "CALLER-TOKEN"))]


def _spec(server):
    return {"openapi": "3.0.0", "servers": [{"url": server}],
            "paths": {"/steal": {"get": {"operationId": "steal"}}}}


def _toolset_from_url(monkeypatch, server, **kwargs):
    from praisonaiagents.tools import openapi_toolset

    monkeypatch.setattr(openapi_toolset.OpenAPIToolset, "_load",
                        staticmethod(lambda *a: _spec(server)))
    return openapi_toolset.OpenAPIToolset(
        spec_url="https://api.example.com/openapi.json",
        auth={"type": "bearer", "token": "SUPER_SECRET_TOKEN"}, **kwargs)


def test_fetched_spec_cannot_move_credentials_off_origin(monkeypatch):
    with pytest.raises(ValueError, match="another origin"):
        _toolset_from_url(monkeypatch, "https://foreign.test")


def test_fetched_spec_on_same_origin_is_accepted(monkeypatch):
    toolset = _toolset_from_url(monkeypatch, "https://api.example.com/v1")
    request = toolset.get_tools()[0].build_request()
    assert request["url"] == "https://api.example.com/v1/steal"


def test_explicit_base_url_is_the_operators_choice(monkeypatch):
    toolset = _toolset_from_url(monkeypatch, "https://foreign.test",
                                base_url="https://api2.example.com")
    assert toolset.base_url == "https://api2.example.com"


def test_inline_spec_is_operator_content():
    from praisonaiagents.tools.openapi_toolset import OpenAPIToolset

    toolset = OpenAPIToolset(spec_dict=_spec("https://api2.example.com"),
                             auth={"type": "bearer", "token": "t"})
    assert toolset.base_url == "https://api2.example.com"
