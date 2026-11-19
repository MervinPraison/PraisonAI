"""session_search returns only the calling user's (or agent's) sessions.

A bot sets the platform user id in the session context for each turn; the tool
then sees only sessions recorded for that user. With no user id (single-user
setups) it sees only sessions of the calling agent. With neither, it refuses.
"""
import json

import pytest

from praisonaiagents.session.context import clear_session_context, set_session_context
from praisonaiagents.session.store import DefaultSessionStore
from praisonaiagents.tools.injected import AgentState, with_injection_context
from praisonaiagents.tools.session_tools import SessionTools

SECRET = "my card PIN is BOB-SECRET-4321"


@pytest.fixture
def tools(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("PRAISONAI_HOME", str(tmp_path / ".praisonai"))
    store = DefaultSessionStore(session_dir=str(tmp_path / "sessions"))
    for sid, agent, user, text in (
        ("telegram:alice", "support", "alice", "hello from alice about my PIN reset"),
        ("telegram:bob", "support", "bob", SECRET),
        ("cli-run", "writer", "", "writer draft PIN notes"),
    ):
        store.set_agent_info(sid, agent_name=agent, user_id=user or None)
        store.add_user_message(sid, text)
    return SessionTools(store=store)


@pytest.fixture
def as_user():
    tokens = []

    def _set(user_id):
        tokens.append(set_session_context(platform="telegram", user_id=user_id))

    yield _set
    for token in reversed(tokens):
        clear_session_context(token)


def _call(tools, **kwargs):
    return json.loads(tools.session_search(**kwargs))


def test_user_b_cannot_find_user_a_session(tools, as_user):
    as_user("alice")
    found = json.dumps(_call(tools, query="PIN"))
    assert "BOB-SECRET-4321" not in found
    assert "hello from alice" in found  # control: alice still finds her own
    assert "BOB-SECRET-4321" not in json.dumps(_call(tools))  # browse
    scroll = _call(tools, session_id="telegram:bob")
    assert "BOB-SECRET-4321" not in json.dumps(scroll)


def test_without_a_user_id_the_agent_name_scopes(tools):
    state = AgentState(agent_id="writer", run_id="r", session_id="cli-run", metadata={"agent_name": "writer"})
    with with_injection_context(state):
        found = json.dumps(_call(tools, query="PIN"))
    assert "writer draft" in found
    assert "BOB-SECRET-4321" not in found and "hello from alice" not in found


def test_no_caller_scope_refuses(tools):
    out = _call(tools, query="PIN")
    assert out["success"] is False
    assert "BOB-SECRET-4321" not in json.dumps(out)
