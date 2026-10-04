"""Portable imports refresh the indexed store's content and routing views."""

import pytest
import threading
import os
import sqlite3
from concurrent.futures import ThreadPoolExecutor

from praisonaiagents.session.sqlite_store import SqliteSessionStore
from praisonaiagents.session.store import DefaultSessionStore, FileLock


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

    def delayed_save(store, session, *, overwrite=True):
        result = original(store, session, overwrite=overwrite)
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
    assert [hit.session_id for hit in destination.search("narwhal")] == ["session"]
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


@pytest.mark.parametrize("peer_kind", [DefaultSessionStore, SqliteSessionStore])
def test_failed_refresh_compares_index_to_replacement_peer_file(make_store, monkeypatch, peer_kind):
    source = make_store(DefaultSessionStore)
    assert source.add_message("session", "user", "imported pelican")
    destination = make_store(SqliteSessionStore)
    assert destination.add_message("session", "user", "old otter")
    assert destination.set_gateway_info("session", gateway_session_id="old-route", agent_id="old-agent")
    kwargs = {"db_path": destination.db_path} if peer_kind is SqliteSessionStore else {}
    peer = peer_kind(session_dir=destination.session_dir, **kwargs)
    invalidate = destination._invalidate_import_index

    def unavailable(*args):
        raise OSError("post-import read unavailable")

    def replace_then_invalidate(session):
        # The failed refresh has released FileLock. A JSON-only peer cannot
        # refresh SQLite, whereas an indexed peer can publish a correct view.
        assert peer.set_chat_history("session", [{"role": "user", "content": "newer narwhal"}])
        assert peer.set_gateway_info("session", gateway_session_id="new-route", agent_id="new-agent")
        invalidate(session)

    monkeypatch.setattr(destination, "_load_session_from_disk", unavailable)
    monkeypatch.setattr(destination, "_invalidate_import_index", replace_then_invalidate)
    try:
        assert destination.import_sessions(source.export_all(), overwrite=True).imported == 1
        conn = destination._connect()
        if peer_kind is DefaultSessionStore:
            for table in ("session_fts", "session_meta", "session_route"):
                assert conn.execute(f"SELECT session_id FROM {table} WHERE session_id = ?", ("session",)).fetchall() == []
        else:
            assert conn.execute("SELECT content FROM session_fts WHERE session_id = ?", ("session",)).fetchall() == [("newer narwhal",)]
            assert conn.execute("SELECT gateway_session_id, agent_id FROM session_route WHERE session_id = ?", ("session",)).fetchall() == [("new-route", "new-agent")]
        assert DefaultSessionStore(session_dir=destination.session_dir).get_chat_history("session") == [{"role": "user", "content": "newer narwhal"}]
    finally:
        conn = getattr(peer, "_conn", None)
        if conn is not None:
            conn.close()


@pytest.mark.parametrize("body_failure", [False, True])
def test_failed_index_commit_releases_transaction_and_preserves_old_views(make_store, body_failure):
    destination = make_store(SqliteSessionStore)
    assert destination.add_message("session", "user", "old otter")
    assert destination.set_gateway_info("session", gateway_session_id="old-route", agent_id="old-agent")
    conn = destination._connect()
    conn.execute("PRAGMA journal_mode=DELETE")
    conn.execute("PRAGMA busy_timeout=10")
    source = make_store(DefaultSessionStore)
    assert source.add_message("session", "user", "new narwhal")
    assert source.set_gateway_info("session", gateway_session_id="new-route", agent_id="new-agent")
    replacement = source.get_session("session")
    if body_failure:
        conn.execute("CREATE TRIGGER fail_metadata BEFORE INSERT ON session_meta "
                     "BEGIN SELECT RAISE(FAIL, 'injected body failure'); END")
    reader = sqlite3.connect(destination.db_path, isolation_level=None)
    try:
        reader.execute("BEGIN")
        assert reader.execute("SELECT content FROM session_fts WHERE session_id = 'session'").fetchone() == ("old otter",)
        assert destination._index_session(replacement) is False
        assert not conn.in_transaction, "failed refresh leaked its outer write transaction"
    finally:
        reader.close()
    if body_failure:
        conn.execute("DROP TRIGGER fail_metadata")
    assert conn.execute("SELECT content FROM session_fts WHERE session_id = 'session'").fetchone() == ("old otter",)
    assert conn.execute("SELECT gateway_session_id, agent_id FROM session_route WHERE session_id = 'session'").fetchone() == ("old-route", "old-agent")
    # A later refresh must commit independently and become visible to peers.
    assert destination._index_session(replacement)
    peer = sqlite3.connect(destination.db_path, isolation_level=None)
    try:
        assert peer.execute("SELECT content FROM session_fts WHERE session_id = 'session'").fetchone() == ("new narwhal",)
        assert peer.execute("SELECT gateway_session_id, agent_id FROM session_route WHERE session_id = 'session'").fetchone() == ("new-route", "new-agent")
        peer.execute("BEGIN IMMEDIATE")
        peer.execute("ROLLBACK")
    finally:
        peer.close()


def test_failed_nested_index_refresh_preserves_callers_transaction(make_store):
    destination = make_store(SqliteSessionStore)
    assert destination.add_message("session", "user", "old otter")
    conn = destination._connect()
    conn.execute("CREATE TRIGGER fail_metadata BEFORE INSERT ON session_meta "
                 "WHEN NEW.session_id = 'session' "
                 "BEGIN SELECT RAISE(FAIL, 'injected body failure'); END")
    conn.execute("BEGIN")
    conn.execute("INSERT INTO session_meta VALUES ('unrelated', 'caller-pending')")
    assert destination._index_session(destination.get_session("session")) is False
    assert conn.in_transaction
    assert conn.execute("SELECT updated_at FROM session_meta WHERE session_id = 'unrelated'").fetchone() == ("caller-pending",)
    assert conn.execute("SELECT content FROM session_fts WHERE session_id = 'session'").fetchone() == ("old otter",)
    conn.execute("COMMIT")


def test_import_and_initial_backfill_do_not_invert_file_database_locks(make_store, monkeypatch):
    from praisonaiagents.session import sqlite_store as indexed_module
    from praisonaiagents.session import store as store_module

    source = make_store(DefaultSessionStore)
    assert source.add_message("session", "user", "imported narwhal")
    destination = make_store(SqliteSessionStore, lock_timeout=0.3)
    destination._connect()
    import_holds_file = threading.Event()
    backfill_attempts_file = threading.Event()
    release_import = threading.Event()
    failed_locks = []
    original_load = destination._load_session_from_disk

    class ObservedFileLock(FileLock):
        def acquire(self):
            if threading.current_thread().name.startswith("backfill"):
                backfill_attempts_file.set()
            acquired = super().acquire()
            if not acquired:
                failed_locks.append(self.filepath)
            return acquired

    def load(session_id, filepath):
        if threading.current_thread().name.startswith("import"):
            import_holds_file.set()
            assert release_import.wait(5)
        return original_load(session_id, filepath)

    monkeypatch.setattr(indexed_module, "FileLock", ObservedFileLock)
    monkeypatch.setattr(store_module, "FileLock", ObservedFileLock)
    monkeypatch.setattr(destination, "_load_session_from_disk", load)
    with ThreadPoolExecutor(max_workers=1, thread_name_prefix="import") as imports, ThreadPoolExecutor(max_workers=1, thread_name_prefix="backfill") as reads:
        restoring = imports.submit(destination.import_sessions, source.export_all())
        try:
            assert import_holds_file.wait(5)
            searching = reads.submit(destination.search, "narwhal")
            assert backfill_attempts_file.wait(5)
        finally:
            release_import.set()
        assert restoring.result(timeout=5).imported == 1
        assert [hit.session_id for hit in searching.result(timeout=5)] == ["session"]
    assert failed_locks == [], "backfill retained the DB lock while waiting for import's file lock"


@pytest.mark.parametrize("failure", ["file_lock", "sql_refresh"])
def test_initial_backfill_retries_after_a_failed_transcript(make_store, failure):
    destination = make_store(SqliteSessionStore, lock_timeout=0.05)
    plain = DefaultSessionStore(session_dir=destination.session_dir)
    assert plain.add_message("legacy", "user", "legacy narwhal")
    assert plain.set_gateway_info("legacy", gateway_session_id="legacy-route", agent_id="legacy-agent")
    conn = destination._connect()
    if failure == "file_lock":
        with FileLock(plain._get_session_path("legacy")):
            assert destination.search("narwhal") == []
    else:
        conn.execute("CREATE TRIGGER fail_metadata BEFORE INSERT ON session_meta "
                     "BEGIN SELECT RAISE(FAIL, 'backfill failed'); END")
        assert destination.search("narwhal") == []
        conn.execute("DROP TRIGGER fail_metadata")
    assert [hit.session_id for hit in destination.search("narwhal")] == ["legacy"]
    assert destination.get_by_gateway_session("legacy-route").session_id == "legacy"
    assert destination.list_sessions_by_gateway_agent("legacy-agent") == ["legacy"]


@pytest.mark.parametrize("failure", ["file_lock", "sql_refresh"])
def test_upgrade_backfill_does_not_rebuild_successful_sessions_on_retry(make_store, failure):
    destination = make_store(SqliteSessionStore, lock_timeout=0.02)
    plain = DefaultSessionStore(session_dir=destination.session_dir)
    for sid in ("healthy", "unavailable"):
        assert plain.add_message(sid, "user", sid + " narwhal")
        assert plain.set_gateway_info(sid, gateway_session_id=sid + "-route")
    conn = destination._connect()
    destination._set_index_content_version(conn, destination.INDEX_CONTENT_VERSION - 1)
    conn.execute("CREATE TABLE backfill_writes (session_id TEXT)")
    conn.execute("CREATE TRIGGER observe_backfill AFTER INSERT ON session_meta "
                 "BEGIN INSERT INTO backfill_writes VALUES (NEW.session_id); END")
    lock = FileLock(plain._get_session_path("unavailable"))
    if failure == "file_lock":
        lock.acquire()
    else:
        conn.execute("CREATE TRIGGER fail_backfill BEFORE INSERT ON session_meta "
                     "WHEN NEW.session_id = 'unavailable' "
                     "BEGIN SELECT RAISE(FAIL, 'unavailable transcript'); END")
    try:
        for _ in range(3):
            assert [hit.session_id for hit in destination.search("healthy")] == ["healthy"]
            assert destination.get_by_gateway_session("healthy-route").session_id == "healthy"
        assert conn.execute("SELECT COUNT(*) FROM backfill_writes WHERE session_id = 'healthy'").fetchone() == (1,)
        assert destination._index_content_version(conn) == destination.INDEX_CONTENT_VERSION - 1
    finally:
        if failure == "file_lock":
            lock.release()
        else:
            conn.execute("DROP TRIGGER fail_backfill")
    assert destination.get_by_gateway_session("unavailable-route").session_id == "unavailable"
    assert conn.execute("SELECT COUNT(*) FROM backfill_writes WHERE session_id = 'healthy'").fetchone() == (1,)
    assert conn.execute("SELECT COUNT(*) FROM backfill_writes WHERE session_id = 'unavailable'").fetchone() == (1,)
    assert destination._index_content_version(conn) == destination.INDEX_CONTENT_VERSION


@pytest.mark.parametrize("failure", ["file_lock", "sql_refresh"])
@pytest.mark.parametrize("peer_kind", [DefaultSessionStore, SqliteSessionStore])
def test_upgrade_retry_reindexes_a_peer_changed_transcript(make_store, failure, peer_kind):
    destination = make_store(SqliteSessionStore, lock_timeout=0.02)
    plain = DefaultSessionStore(session_dir=destination.session_dir)
    assert plain.add_message("healthy", "user", "old otter")
    assert plain.set_gateway_info("healthy", gateway_session_id="old-route", agent_id="old-agent")
    assert plain.add_message("unavailable", "user", "blocked pelican")
    conn = destination._connect()
    destination._set_index_content_version(conn, destination.INDEX_CONTENT_VERSION - 1)
    lock = FileLock(plain._get_session_path("unavailable"))
    if failure == "file_lock":
        lock.acquire()
    else:
        conn.execute("CREATE TRIGGER fail_backfill BEFORE INSERT ON session_meta "
                     "WHEN NEW.session_id = 'unavailable' "
                     "BEGIN SELECT RAISE(FAIL, 'unavailable transcript'); END")
    try:
        assert [hit.session_id for hit in destination.search("otter")] == ["healthy"]
        assert destination._index_content_version(conn) == destination.INDEX_CONTENT_VERSION - 1
        kwargs = {"db_path": destination.db_path} if peer_kind is SqliteSessionStore else {}
        peer = peer_kind(session_dir=destination.session_dir, **kwargs)
        try:
            assert peer.set_chat_history("healthy", [{"role": "user", "content": "newer narwhal"}])
            assert peer.set_gateway_info("healthy", gateway_session_id="new-route", agent_id="new-agent")
        finally:
            peer_conn = getattr(peer, "_conn", None)
            if peer_conn is not None:
                peer_conn.close()
    finally:
        if failure == "file_lock":
            lock.release()
        else:
            conn.execute("DROP TRIGGER fail_backfill")
    assert [hit.session_id for hit in destination.search("narwhal")] == ["healthy"]
    assert destination.search("otter") == []
    assert destination.get_by_gateway_session("old-route") is None
    assert destination.get_by_gateway_session("new-route").session_id == "healthy"
    assert destination.list_sessions_by_gateway_agent("old-agent") == []
    assert destination.list_sessions_by_gateway_agent("new-agent") == ["healthy"]
    assert destination._index_content_version(conn) == destination.INDEX_CONTENT_VERSION


@pytest.mark.parametrize("reader", ["gateway", "agent"])
@pytest.mark.parametrize("unreadable", [False, True])
def test_unknown_import_generation_does_not_reuse_obsolete_routes(make_store, monkeypatch, reader, unreadable):
    source = make_store(DefaultSessionStore)
    assert source.add_message("session", "user", "replacement")
    assert source.set_gateway_info("session", gateway_session_id="new-gateway", agent_id="new-agent")
    destination = make_store(SqliteSessionStore)
    assert destination.add_message("session", "user", "old")
    assert destination.set_gateway_info("session", gateway_session_id="old-gateway", agent_id="old-agent")
    assert destination.get_by_gateway_session("old-gateway") is not None
    monkeypatch.setattr(destination, "_session_file_identity", lambda *_: None)
    monkeypatch.setattr(destination, "_index_session", lambda *_: False)
    assert destination.import_sessions(source.export_all(), overwrite=True).imported == 1
    assert destination._connect().execute("SELECT gateway_session_id FROM session_route WHERE session_id = ?", ("session",)).fetchone() == ("old-gateway",)
    if unreadable:
        import builtins
        original_open = builtins.open
        path = destination._get_session_path("session")

        def fail_transcript_open(filename, *args, **kwargs):
            if os.fspath(filename) == path and (not args or "r" in args[0]):
                raise PermissionError("temporarily unreadable transcript")
            return original_open(filename, *args, **kwargs)

        monkeypatch.setattr(builtins, "open", fail_transcript_open)
    if reader == "gateway":
        assert destination.get_by_gateway_session("old-gateway") is None
    else:
        assert destination.list_sessions_by_gateway_agent("old-agent") == []


def test_gateway_agent_limit_counts_verified_routes(make_store):
    destination = make_store(SqliteSessionStore)
    for sid in ["stale", "valid"]:
        assert destination.add_message(sid, "user", sid)
        assert destination.set_gateway_info(sid, agent_id="agent")
    assert len(destination.list_sessions_by_gateway_agent("agent")) == 2
    peer = DefaultSessionStore(session_dir=destination.session_dir)
    assert peer.set_gateway_info("stale", agent_id="other-agent")
    assert destination.list_sessions_by_gateway_agent("agent", limit=1) == ["valid"]


def test_gateway_route_read_failure_does_not_use_warm_cache(make_store, monkeypatch):
    destination = make_store(SqliteSessionStore)
    assert destination.add_message("session", "user", "old")
    assert destination.set_gateway_info("session", gateway_session_id="old-gateway", agent_id="old-agent")
    assert destination.get_by_gateway_session("old-gateway") is not None
    peer = DefaultSessionStore(session_dir=destination.session_dir)
    assert peer.set_gateway_info("session", gateway_session_id="new-gateway", agent_id="new-agent")

    def fail_read(*_):
        raise PermissionError("transient route read failure")

    with monkeypatch.context() as blocked:
        blocked.setattr(destination, "_load_session_from_disk", fail_read)
        assert destination.get_by_gateway_session("old-gateway") is None
        assert destination.list_sessions_by_gateway_agent("old-agent") == []
    assert destination.get_by_gateway_session("old-gateway") is None
    assert destination.list_sessions_by_gateway_agent("old-agent") == []
    assert peer.get_by_gateway_session("new-gateway").session_id == "session"


@pytest.mark.parametrize("restart", [False, True])
@pytest.mark.parametrize("failure", ["read", "index", "unknown"])
def test_failed_import_recovers_new_recall_and_routes(make_store, monkeypatch, restart, failure):
    source = make_store(DefaultSessionStore)
    assert source.add_message("session", "user", "new narwhal")
    assert source.set_gateway_info("session", gateway_session_id="new-route", agent_id="new-agent")
    destination = make_store(SqliteSessionStore)
    assert destination.add_message("session", "user", "old otter")
    assert destination.set_gateway_info("session", gateway_session_id="old-route", agent_id="old-agent")
    assert destination.get_by_gateway_session("old-route") is not None
    with monkeypatch.context() as blocked:
        if failure == "read":
            def fail_read(*_):
                raise PermissionError("temporarily unreadable")
            blocked.setattr(destination, "_load_session_from_disk", fail_read)
        else:
            blocked.setattr(destination, "_index_session", lambda *_: False)
        if failure == "unknown":
            blocked.setattr(destination, "_session_file_identity", lambda *_: None)
        assert destination.import_sessions(source.export_all(), overwrite=True, reset_live_fields=False).imported == 1
        assert destination.get_by_gateway_session("old-route") is None
    if restart:
        reopened = SqliteSessionStore(session_dir=destination.session_dir, db_path=destination.db_path)
        try:
            assert [hit.session_id for hit in reopened.search("narwhal")] == ["session"]
            assert reopened.get_by_gateway_session("new-route").session_id == "session"
            assert reopened.list_sessions_by_gateway_agent("new-agent") == ["session"]
            assert reopened.get_by_gateway_session("old-route") is None
            assert reopened.search("otter") == []
        finally:
            reopened._conn.close()
        return
    assert [hit.session_id for hit in destination.search("narwhal")] == ["session"]
    assert destination.search("otter") == []
    assert destination.get_by_gateway_session("new-route").session_id == "session"
    assert destination.list_sessions_by_gateway_agent("new-agent") == ["session"]
    assert destination.get_by_gateway_session("old-route") is None
    assert destination._connect().execute("SELECT content FROM session_fts WHERE session_id = ?", ("session",)).fetchall() == [("new narwhal",)]


@pytest.mark.parametrize("peer_kind", [DefaultSessionStore, SqliteSessionStore])
def test_import_retry_indexes_current_peer_and_does_not_rewrite_healthy_rows(make_store, peer_kind):
    destination = make_store(SqliteSessionStore)
    for sid in ("session", "healthy"):
        assert destination.add_message(sid, "user", "old otter")
        assert destination.set_gateway_info(sid, gateway_session_id=sid + "-route")
    assert destination.search("otter")
    conn = destination._connect()
    conn.execute("CREATE TABLE observed_writes (session_id TEXT)")
    conn.execute("CREATE TRIGGER observe_retry AFTER INSERT ON session_meta "
                 "BEGIN INSERT INTO observed_writes VALUES (NEW.session_id); END")
    conn.execute("CREATE TRIGGER fail_retry BEFORE INSERT ON session_meta "
                 "WHEN NEW.session_id = 'session' BEGIN SELECT RAISE(FAIL, 'retry unavailable'); END")
    source = make_store(DefaultSessionStore)
    assert source.add_message("session", "user", "imported narwhal")
    assert destination.import_sessions(source.export_all(), overwrite=True).imported == 1
    for _ in range(2):
        assert destination.search("narwhal") == []
        assert destination.get_by_gateway_session("healthy-route").session_id == "healthy"
    assert conn.execute("SELECT COUNT(*) FROM observed_writes").fetchone() == (0,)
    conn.execute("DROP TRIGGER fail_retry")
    kwargs = {"db_path": destination.db_path} if peer_kind is SqliteSessionStore else {}
    peer = peer_kind(session_dir=destination.session_dir, **kwargs)
    try:
        assert peer.set_chat_history("session", [{"role": "user", "content": "newer penguin"}])
        assert peer.set_gateway_info("session", gateway_session_id="peer-route", agent_id="peer-agent")
    finally:
        if getattr(peer, "_conn", None) is not None:
            peer._conn.close()
    assert destination.get_by_gateway_session("peer-route").session_id == "session"
    assert [hit.session_id for hit in destination.search("penguin")] == ["session"]
    assert destination.search("narwhal") == []
    assert destination.get_by_gateway_session("session-route") is None
    assert conn.execute("SELECT key FROM session_index_meta WHERE key = 'import_pending:session'").fetchone() is None
    assert conn.execute("SELECT COUNT(*) FROM observed_writes WHERE session_id = 'healthy'").fetchone() == (0,)
