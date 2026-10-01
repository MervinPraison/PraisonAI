"""Clearing active turns preserves the session's routing and archived recall."""

import pytest
import threading
from concurrent.futures import ThreadPoolExecutor

from praisonaiagents.session.sqlite_store import SqliteSessionStore
from praisonaiagents.session.store import DefaultSessionStore


@pytest.fixture
def make_store(tmp_path):
    stores = []

    def create(kind, **kwargs):
        store = kind(session_dir=str(tmp_path / str(len(stores))), **kwargs)
        stores.append(store)
        return store

    yield create
    for store in stores:
        conn = getattr(store, "_conn", None)
        if conn is not None:
            conn.close()


@pytest.mark.parametrize("kind", [DefaultSessionStore, SqliteSessionStore])
@pytest.mark.parametrize("warm", ["cold", "search", "route"])
def test_clear_preserves_gateway_and_agent_routes(make_store, kind, warm):
    store = make_store(kind)
    assert store.add_message("session", "user", "pelican notes")
    assert store.set_gateway_info("session", gateway_session_id="gateway", agent_id="agent")
    if warm == "search":
        assert store.search("pelican")
    elif warm == "route":
        assert store.get_by_gateway_session("gateway") is not None

    assert store.clear_session("session")
    session = store.get_session("session")
    assert session.messages == []
    assert session.gateway_session_id == "gateway"
    assert session.agent_id == "agent"
    found = store.get_by_gateway_session("gateway")
    assert found is not None and found.session_id == "session"
    assert store.list_sessions_by_gateway_agent("agent") == ["session"]
    assert store.search("pelican") == []

    assert store.add_message("session", "user", "narwhal notes")
    assert [hit.session_id for hit in store.search("narwhal")] == ["session"]
    assert store.delete_session("session")
    assert store.get_by_gateway_session("gateway") is None
    assert store.list_sessions_by_gateway_agent("agent") == []
    assert store.search("narwhal") == []


@pytest.mark.parametrize("kind", [DefaultSessionStore, SqliteSessionStore])
def test_clear_keeps_archived_turns_searchable(make_store, kind):
    store = make_store(kind, active_window=3)
    assert store.add_message("session", "user", "archived pelican marker")
    for index in range(8):
        assert store.add_message("session", "user", f"later turn {index}")
    before = store.get_session("session")
    assert any("pelican" in message.content for message in before.archived_messages)
    assert store.search("pelican")

    assert store.clear_session("session")
    after = store.get_session("session")
    assert after.messages == []
    assert after.archived_messages == before.archived_messages
    hits = store.search("pelican")
    assert [hit.session_id for hit in hits] == ["session"]
    assert any(message["archived"] for message in hits[0].messages)


@pytest.mark.parametrize("separate_store", [False, True])
def test_delete_before_clear_index_refresh_does_not_restore_route(make_store, monkeypatch, separate_store):
    store = make_store(SqliteSessionStore)
    assert store.add_message("session", "user", "pelican notes")
    assert store.set_gateway_info("session", gateway_session_id="gateway", agent_id="agent")
    assert store.get_by_gateway_session("gateway") is not None
    deleting = store
    if separate_store:
        deleting = SqliteSessionStore(session_dir=store.session_dir, db_path=store.db_path)
        assert deleting.get_by_gateway_session("gateway") is not None

    read_complete = threading.Event()
    resume = threading.Event()
    original = store._index_session

    def delayed_index(session):
        read_complete.set()
        assert resume.wait(5), "delete did not release the delayed refresh"
        original(session)

    monkeypatch.setattr(store, "_index_session", delayed_index)
    try:
        with ThreadPoolExecutor(max_workers=1) as executor:
            clearing = executor.submit(store.clear_session, "session")
            try:
                assert read_complete.wait(5), "clear did not reach index refresh"
                assert deleting.delete_session("session")
            finally:
                resume.set()
            assert clearing.result(timeout=5)
        assert not store.session_exists("session")
        assert store.list_sessions_by_gateway_agent("agent") == []
        assert store.get_by_gateway_session("gateway") is None
    finally:
        if separate_store and deleting._conn is not None:
            deleting._conn.close()
