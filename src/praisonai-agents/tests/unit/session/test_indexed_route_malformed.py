"""An unreadable indexed transcript must not interrupt gateway routing."""

import json

import pytest

from praisonaiagents.session import SqliteSessionStore
from praisonaiagents.session.store import DefaultSessionStore


@pytest.mark.parametrize("field", ["messages", "archived_messages"])
@pytest.mark.parametrize("entry", [None, "invalid", 42])
def test_malformed_indexed_messages_do_not_interrupt_routes(tmp_path, monkeypatch, caplog, field, entry):
    """Preserve malformed indexed files while healthy routes remain usable."""
    store = SqliteSessionStore(session_dir=str(tmp_path))
    store.add_message("broken", "user", "original")
    store.set_gateway_info("broken", gateway_session_id="gw-broken", agent_id="agent")
    store.add_message("healthy", "user", "retained")
    store.set_gateway_info("healthy", gateway_session_id="gw-healthy", agent_id="agent")
    store._ensure_backfilled()
    path = tmp_path / "broken.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data[field] = [entry]
    path.write_text(json.dumps(data), encoding="utf-8")
    original = path.read_bytes()
    events = []
    monkeypatch.setattr(store, "_fire_corruption_hook", lambda *args: events.append(args))

    assert store.get_by_gateway_session("gw-broken") is None
    assert store.get_by_gateway_session("gw-healthy").session_id == "healthy"
    assert store.list_sessions_by_gateway_agent("agent") == ["healthy"]
    assert path.read_bytes() == original
    assert len(events) == 2
    assert all(event[0] == "broken" and event[2] is None for event in events)
    assert "Skipping unreadable session file" in caplog.text
    assert store._connect().execute(
        "SELECT session_id FROM session_route WHERE session_id = 'broken'"
    ).fetchone() == ("broken",)


@pytest.mark.parametrize("mode", ["plain", "unavailable", "query_failure"])
@pytest.mark.parametrize("field", ["messages", "archived_messages"])
@pytest.mark.parametrize("entry", [None, "invalid", 42])
def test_malformed_messages_do_not_interrupt_fallback_routes(tmp_path, monkeypatch, caplog, mode, field, entry):
    """The JSON scan also contains malformed matching transcripts."""
    cls = DefaultSessionStore if mode == "plain" else SqliteSessionStore
    store = cls(session_dir=str(tmp_path))
    store.add_message("broken", "user", "original")
    store.set_gateway_info("broken", gateway_session_id="gw-broken", agent_id="agent")
    store.add_message("healthy", "user", "retained")
    store.set_gateway_info("healthy", gateway_session_id="gw-healthy", agent_id="agent")
    if mode != "plain":
        store._ensure_backfilled()
    if mode == "unavailable":
        monkeypatch.setattr(store, "_connect", lambda: None)
    elif mode == "query_failure":
        store._connect().execute("DROP TABLE session_route")
    path = tmp_path / "broken.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data[field] = [entry]
    path.write_text(json.dumps(data), encoding="utf-8")
    original = path.read_bytes()
    events = []
    monkeypatch.setattr(store, "_fire_corruption_hook", lambda *args: events.append(args))

    assert store.get_by_gateway_session("gw-broken") is None
    assert store.get_by_gateway_session("gw-healthy").session_id == "healthy"
    assert path.read_bytes() == original
    assert len(events) == 1 and events[0][0] == "broken" and events[0][2] is None
    assert "Skipping unreadable session file" in caplog.text
