"""G-19: the history block of Agent.__init__ as a pure function.

Expected values were measured on main before the move. Session files are
looked up in a temp PRAISONAI_HOME, and the workspace id is pinned.
"""
import hashlib

import pytest

from praisonaiagents import Agent
from praisonaiagents.config.agent_init import resolve_agent_history
from praisonaiagents.config.feature_configs import MemoryConfig


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("PRAISONAI_HOME", str(tmp_path))
    monkeypatch.delenv("PRAISONAI_GLOBAL_SESSIONS", raising=False)
    monkeypatch.setattr("praisonaiagents.session.workspace.workspace_id", lambda: "ws1")
    from praisonaiagents.paths import get_sessions_dir
    d = get_sessions_dir()
    d.mkdir(parents=True, exist_ok=True)
    return d


def _sha(text):
    return "history_" + hashlib.sha256(text.encode()).hexdigest()[:8]


def _md5(text):
    return "history_" + hashlib.md5(text.encode()).hexdigest()[:8]


HISTORY = MemoryConfig(history=True)


def test_no_history(home):
    assert resolve_agent_history(None, None, None, "bob") == (False, 10, None, None)
    assert resolve_agent_history(MemoryConfig(), "s", "as", "bob") == (False, 10, None, "s")


def test_explicit_ids(home):
    cfg = MemoryConfig(history=True, history_limit=5, session_id="s1")
    assert resolve_agent_history(cfg, None, None, "bob") == (True, 5, "s1", "s1")
    assert resolve_agent_history(HISTORY, None, "as1", "bob") == (True, 10, "as1", "as1")
    assert resolve_agent_history(HISTORY, "given", None, "bob") == (True, 10, None, "given")


def test_generated_workspace_id(home):
    new = _sha("ws1:bob")
    assert resolve_agent_history(HISTORY, None, None, "bob") == (True, 10, new, new)
    # A legacy name-only file is NOT adopted in workspace scope (Issue #3154).
    (home / f"{_sha('bob')}.json").write_text("{}")
    assert resolve_agent_history(HISTORY, None, None, "bob")[3] == new
    # No name -> "agent".
    assert resolve_agent_history(HISTORY, None, None, None)[3] == _sha("ws1:agent")


def test_global_scope_adopts_legacy_files(home, monkeypatch):
    monkeypatch.setenv("PRAISONAI_GLOBAL_SESSIONS", "true")
    assert resolve_agent_history(HISTORY, None, None, "bob")[3] == _sha("global:bob")
    (home / f"{_md5('bob')}.json").write_text("{}")
    assert resolve_agent_history(HISTORY, None, None, "bob")[3] == _md5("bob")
    (home / f"{_sha('bob')}.json").write_text("{}")
    assert resolve_agent_history(HISTORY, None, None, "bob")[3] == _sha("bob")
    (home / f"{_sha('global:bob')}.json").write_text("{}")
    assert resolve_agent_history(HISTORY, None, None, "bob")[3] == _sha("global:bob")


@pytest.mark.parametrize("memory", [None, MemoryConfig(history=True, history_limit=5, session_id="s1"),
                                    MemoryConfig(history=True)])
def test_agent_stores_what_the_resolver_returns(home, monkeypatch, memory):
    monkeypatch.setenv("OPENAI_API_KEY", "x")
    agent = Agent(name="bob", instructions="x", memory=memory)
    enabled, limit, hist_sid, sid = resolve_agent_history(
        agent._memory_config if hasattr(agent, "_memory_config") else memory, None, None, "bob")
    assert (agent._history_enabled, agent._history_limit, agent._history_session_id) == (enabled, limit, hist_sid)
    if enabled:
        assert agent._session_id == sid
