"""Portable imports refresh the indexed store's content and routing views."""

import pytest
import threading
import os
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
        assert destination._cache["session"].messages[0].content == "narwhal newer turn"
        with monkeypatch.context() as fallback:
            def unavailable(*args):
                raise OSError("temporary read failure")

            fallback.setattr(destination, "_load_session_from_disk", unavailable)
            assert destination._read_session_fresh("session").messages[0].content == "narwhal newer turn"
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


@pytest.mark.parametrize("existing_index", [False, True])
@pytest.mark.parametrize("stat_failure", [False, True])
def test_failed_import_refresh_preserves_new_peer_index(make_store, monkeypatch, existing_index, stat_failure):
    source = make_store(DefaultSessionStore)
    assert source.add_message("session", "user", "imported pelican")
    destination = make_store(SqliteSessionStore)
    if existing_index:
        assert destination.add_message("session", "user", "old otter")
    destination.search("pelican")
    peer = SqliteSessionStore(session_dir=destination.session_dir, db_path=destination.db_path)
    original = DefaultSessionStore._save_imported_session
    original_stat = os.stat

    def unavailable_stat(path, *args, **kwargs):
        if os.fspath(path) == destination._get_session_path("session"):
            raise OSError("path stat temporarily unavailable")
        return original_stat(path, *args, **kwargs)

    def save_then_peer_write(store, session, **kwargs):
        saved = original(store, session, **kwargs)
        assert peer.set_chat_history("session", [{"role": "user", "content": "newer narwhal"}])
        assert peer.set_gateway_info("session", gateway_session_id="new-route", agent_id="new-agent")
        if stat_failure:
            monkeypatch.setattr(os, "stat", unavailable_stat)
        return saved

    def unavailable(*args):
        raise OSError("post-import refresh unavailable")

    monkeypatch.setattr(DefaultSessionStore, "_save_imported_session", save_then_peer_write)
    monkeypatch.setattr(destination, "_load_session_from_disk", unavailable)
    try:
        assert destination.import_sessions(source.export_all(), overwrite=existing_index).imported == 1
        conn = destination._connect()
        assert conn.execute("SELECT content FROM session_fts WHERE session_id = ?", ("session",)).fetchone() == ("newer narwhal",)
        assert conn.execute("SELECT gateway_session_id, agent_id FROM session_route WHERE session_id = ?", ("session",)).fetchone() == ("new-route", "new-agent")
    finally:
        if peer._conn is not None:
            peer._conn.close()


@pytest.mark.parametrize("peer_write", [False, True])
def test_post_import_sql_failure_invalidates_all_old_index_views(make_store, monkeypatch, peer_write):
    source = make_store(DefaultSessionStore)
    assert source.add_message("session", "user", "narwhal replacement")
    destination = make_store(SqliteSessionStore)
    assert destination.add_message("session", "user", "pelican original")
    assert destination.set_gateway_info("session", gateway_session_id="old-gateway", agent_id="old-agent")
    assert destination.search("pelican")
    conn = destination._connect()
    conn.execute("CREATE TRIGGER fail_import_metadata BEFORE INSERT ON session_meta "
                 "BEGIN SELECT RAISE(FAIL, 'injected index failure'); END")
    if peer_write:
        peer = DefaultSessionStore(session_dir=destination.session_dir)
        original = DefaultSessionStore._save_imported_session

        def save_then_peer_write(store, session, **kwargs):
            saved = original(store, session, **kwargs)
            assert peer.set_chat_history("session", [{"role": "user", "content": "narwhal peer replacement"}])
            return saved

        monkeypatch.setattr(DefaultSessionStore, "_save_imported_session", save_then_peer_write)
    report = destination.import_sessions(source.export_all(), overwrite=True)
    assert report.imported == 1
    assert report.skipped == []
    for table in ("session_fts", "session_meta", "session_route"):
        assert conn.execute(f"SELECT session_id FROM {table} WHERE session_id = ?", ("session",)).fetchall() == []
    expected = "narwhal peer replacement" if peer_write else "narwhal replacement"
    assert destination.get_session("session").messages[0].content == expected
    assert destination.get_by_gateway_session("old-gateway") is None
    assert destination.list_sessions_by_gateway_agent("old-agent") == []
    conn.execute("DROP TRIGGER fail_import_metadata")
    assert destination.add_message("session", "user", "recovered update")
    assert [hit.session_id for hit in destination.search("narwhal")] == ["session"]


def test_failed_path_stat_does_not_preserve_stale_import_routes(make_store, monkeypatch):
    source = make_store(DefaultSessionStore)
    assert source.add_message("session", "user", "new imported content")
    destination = make_store(SqliteSessionStore)
    assert destination.add_message("session", "user", "old indexed content")
    assert destination.set_gateway_info("session", gateway_session_id="old-route", agent_id="old-agent")
    assert destination.search("old")
    filepath = destination._get_session_path("session")
    original_stat = os.stat

    def unavailable_stat(path, *args, **kwargs):
        if os.fspath(path) == filepath:
            raise OSError("path stat temporarily unavailable")
        return original_stat(path, *args, **kwargs)

    def unavailable_read(*args):
        raise OSError("post-import read temporarily unavailable")

    with monkeypatch.context() as failures:
        failures.setattr(os, "stat", unavailable_stat)
        failures.setattr(destination, "_load_session_from_disk", unavailable_read)
        report = destination.import_sessions(source.export_all(), overwrite=True)
        assert report.imported == 1
        assert report.skipped == []
        for table in ("session_fts", "session_meta", "session_route"):
            assert destination._conn.execute(f"SELECT session_id FROM {table} WHERE session_id = ?", ("session",)).fetchall() == []
    assert destination.get_session("session").messages[0].content == "new imported content"


@pytest.mark.parametrize("descriptor_identity", [False, True])
def test_failed_refresh_keeps_peer_index_of_same_file_generation(make_store, monkeypatch, descriptor_identity):
    source = make_store(DefaultSessionStore)
    assert source.add_message("session", "user", "imported pelican")
    destination = make_store(SqliteSessionStore)
    assert destination.add_message("session", "user", "old otter")
    peer = SqliteSessionStore(session_dir=destination.session_dir, db_path=destination.db_path)
    original_save = DefaultSessionStore._save_imported_session
    original_index = destination._index_session
    original_identity = destination._session_file_identity

    def save_then_peer_write(store, session, **kwargs):
        saved = original_save(store, session, **kwargs)
        assert peer.set_chat_history("session", [{"role": "user", "content": "newer narwhal"}])
        assert peer.set_gateway_info("session", gateway_session_id="new-route", agent_id="new-agent")
        return saved

    def failed_index_then_peer_indexes_same_generation(fresh):
        conn = destination._connect()
        conn.execute("CREATE TRIGGER fail_once BEFORE INSERT ON session_meta "
                     "BEGIN SELECT RAISE(FAIL, 'injected index failure'); END")
        failed = original_index(fresh)
        conn.execute("DROP TRIGGER fail_once")
        assert failed is False
        assert peer._index_session(fresh)
        return failed

    def identity_using_descriptor(filepath):
        def unavailable(*args, **kwargs):
            raise OSError("path stat temporarily unavailable")
        with monkeypatch.context() as path_failure:
            path_failure.setattr(os, "stat", unavailable)
            return original_identity(filepath)

    monkeypatch.setattr(DefaultSessionStore, "_save_imported_session", save_then_peer_write)
    monkeypatch.setattr(destination, "_index_session", failed_index_then_peer_indexes_same_generation)
    if descriptor_identity:
        monkeypatch.setattr(destination, "_session_file_identity", identity_using_descriptor)
    try:
        assert destination.import_sessions(source.export_all(), overwrite=True).imported == 1
        conn = destination._connect()
        assert conn.execute("SELECT content FROM session_fts WHERE session_id = ?", ("session",)).fetchall() == [("newer narwhal",)]
        assert conn.execute("SELECT gateway_session_id, agent_id FROM session_route WHERE session_id = ?", ("session",)).fetchall() == [("new-route", "new-agent")]
    finally:
        if peer._conn is not None:
            peer._conn.close()
