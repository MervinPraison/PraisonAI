"""An unreadable indexed transcript must not interrupt gateway routing."""

import json

import pytest

from praisonaiagents.session import SqliteSessionStore


@pytest.mark.parametrize("field", ["messages", "archived_messages"])
@pytest.mark.parametrize("entry", [None, "invalid", 42])
def test_malformed_indexed_messages_do_not_interrupt_routes(tmp_path, field, entry):
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

    assert store.get_by_gateway_session("gw-broken") is None
    assert store.get_by_gateway_session("gw-healthy").session_id == "healthy"
    assert store.list_sessions_by_gateway_agent("agent") == ["healthy"]
    assert path.read_bytes() == original
    assert store._connect().execute(
        "SELECT session_id FROM session_route WHERE session_id = 'broken'"
    ).fetchone() == ("broken",)
