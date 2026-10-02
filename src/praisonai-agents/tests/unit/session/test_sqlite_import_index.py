"""Portable imports refresh the indexed store's content and routing views."""

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
@pytest.mark.parametrize("warm", [False, True])
@pytest.mark.parametrize("overwrite", [False, True])
@pytest.mark.parametrize("reset_live_fields", [False, True])
def test_import_refreshes_content_and_routes(make_store, kind, warm, overwrite, reset_live_fields):
    source = make_store(DefaultSessionStore)
    messages = [{"role": "user", "content": f"narwhal imported turn {index}"} for index in range(5)]
    assert source.set_chat_history("session", messages)
    assert source.set_gateway_info("session", gateway_session_id="new-gateway", agent_id="new-agent")
    payload = source.export_all()

    destination = make_store(kind, active_window=2)
    if overwrite:
        assert destination.add_message("session", "user", "pelican old turn")
        assert destination.set_gateway_info("session", gateway_session_id="old-gateway", agent_id="old-agent")
    if warm:
        destination.search("pelican")
        destination.get_by_gateway_session("old-gateway")

    report = destination.import_sessions(payload, overwrite=overwrite, reset_live_fields=reset_live_fields)
    assert report.imported == 1
    assert report.skipped == []
    session = destination.get_session("session")
    assert [message.content for message in session.messages] == [message["content"] for message in messages]
    assert destination.get_by_gateway_session("old-gateway") is None
    assert destination.list_sessions_by_gateway_agent("old-agent") == []
    found = destination.get_by_gateway_session("new-gateway")
    if reset_live_fields:
        assert found is None
        assert destination.list_sessions_by_gateway_agent("new-agent") == []
    else:
        assert found is not None and found.session_id == "session"
        assert destination.list_sessions_by_gateway_agent("new-agent") == ["session"]
    assert destination.search("pelican") == []
    assert [hit.session_id for hit in destination.search("narwhal")] == ["session"]


@pytest.mark.parametrize("write_failure", [False, True])
def test_unsaved_import_keeps_previous_index(make_store, monkeypatch, write_failure):
    source = make_store(DefaultSessionStore)
    assert source.add_message("session", "user", "narwhal replacement")
    destination = make_store(SqliteSessionStore)
    assert destination.add_message("session", "user", "pelican original")
    assert destination.set_gateway_info("session", gateway_session_id="gateway", agent_id="agent")
    assert destination.search("pelican")
    if write_failure:
        monkeypatch.setattr(destination, "_atomic_write_json", lambda *args: False)

    report = destination.import_sessions(source.export_all(), overwrite=write_failure)
    assert report.imported == 0
    assert len(report.skipped) == 1
    assert report.skipped[0]["reason"] == ("write failed" if write_failure else "already exists (use overwrite)")
    assert [hit.session_id for hit in destination.search("pelican")] == ["session"]
    assert destination.search("narwhal") == []
    assert destination.get_by_gateway_session("gateway").session_id == "session"
    assert destination.list_sessions_by_gateway_agent("agent") == ["session"]


def test_warm_import_indexes_archived_turns(make_store):
    source = make_store(DefaultSessionStore, active_window=3)
    assert source.add_message("session", "user", "pelican archived marker")
    for index in range(8):
        assert source.add_message("session", "user", f"later turn {index}")
    assert any("pelican" in message.content for message in source.get_session("session").archived_messages)
    destination = make_store(SqliteSessionStore, active_window=2)
    assert destination.search("pelican") == []
    assert destination.import_sessions(source.export_all()).imported == 1
    hits = destination.search("pelican")
    assert [hit.session_id for hit in hits] == ["session"]
    assert any(message["archived"] for message in hits[0].messages)


@pytest.mark.parametrize("separate_store", [False, True])
def test_write_between_import_save_and_index_keeps_newer_content(make_store, monkeypatch, separate_store):
    source = make_store(DefaultSessionStore)
    assert source.add_message("session", "user", "pelican imported turn")
    destination = make_store(SqliteSessionStore)
    destination.search("pelican")
    writer = destination
    if separate_store:
        writer = SqliteSessionStore(session_dir=destination.session_dir, db_path=destination.db_path)
        writer.search("pelican")

    saved = threading.Event()
    resume = threading.Event()
    original = DefaultSessionStore._save_imported_session

    def delayed_save(store, session, **kwargs):
        result = original(store, session, **kwargs)
        saved.set()
        assert resume.wait(5), "concurrent writer did not finish"
        return result

    monkeypatch.setattr(DefaultSessionStore, "_save_imported_session", delayed_save)
    try:
        with ThreadPoolExecutor(max_workers=1) as executor:
            importing = executor.submit(destination.import_sessions, source.export_all())
            try:
                assert saved.wait(5), "import did not persist the JSON"
                assert writer.set_chat_history("session", [{"role": "user", "content": "narwhal newer turn"}])
                assert writer.set_gateway_info("session", gateway_session_id="new-gateway", agent_id="new-agent")
                assert writer.search("narwhal")
            finally:
                resume.set()
            assert importing.result(timeout=5).imported == 1
        destination.invalidate_cache()
        assert destination.get_session("session").messages[0].content == "narwhal newer turn"
        assert [hit.session_id for hit in destination.search("narwhal")] == ["session"]
        assert destination.search("pelican") == []
        assert destination.get_by_gateway_session("new-gateway").session_id == "session"
        assert destination.list_sessions_by_gateway_agent("new-agent") == ["session"]
    finally:
        if separate_store and writer._conn is not None:
            writer._conn.close()


def test_post_import_refresh_failure_does_not_report_durable_write_failure(make_store, monkeypatch):
    source = make_store(DefaultSessionStore)
    assert source.add_message("session", "user", "durable imported note")
    destination = make_store(SqliteSessionStore)

    def unavailable(*args):
        raise OSError("injected index refresh read failure")

    monkeypatch.setattr(destination, "_load_session_from_disk", unavailable)
    report = destination.import_sessions(source.export_all())
    assert report.imported == 1
    assert report.skipped == []
    reader = DefaultSessionStore(session_dir=destination.session_dir)
    assert reader.get_session("session").messages[0].content == "durable imported note"


def test_post_import_read_failure_does_not_restore_old_routes(make_store, monkeypatch):
    source = make_store(DefaultSessionStore)
    assert source.add_message("session", "user", "narwhal replacement")
    destination = make_store(SqliteSessionStore)
    assert destination.add_message("session", "user", "pelican original")
    assert destination.set_gateway_info("session", gateway_session_id="old-gateway", agent_id="old-agent")
    assert destination.get_by_gateway_session("old-gateway").session_id == "session"
    assert destination.search("pelican")
    original = destination._load_session_from_disk

    def unavailable(*args):
        raise OSError("injected post-save read failure")

    monkeypatch.setattr(destination, "_load_session_from_disk", unavailable)
    report = destination.import_sessions(source.export_all(), overwrite=True)
    assert report.imported == 1
    assert report.skipped == []
    assert destination.get_by_gateway_session("old-gateway") is None
    assert destination.list_sessions_by_gateway_agent("old-agent") == []
    monkeypatch.setattr(destination, "_load_session_from_disk", original)
    destination.invalidate_cache()
    saved = destination.get_session("session")
    assert saved.gateway_session_id is None
    assert saved.agent_id is None
    assert saved.messages[0].content == "narwhal replacement"
    assert destination.search("narwhal") == []
    assert destination.add_message("session", "user", "later update")
    assert [hit.session_id for hit in destination.search("narwhal")] == ["session"]
    assert destination.get_by_gateway_session("old-gateway") is None
