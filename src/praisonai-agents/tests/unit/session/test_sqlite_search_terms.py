"""SQLite candidates must include sessions that the shared term scorer matches."""

import pytest

from praisonaiagents.session.store import DefaultSessionStore
from praisonaiagents.session.sqlite_transcript_store import SqliteTranscriptStore


@pytest.fixture
def sqlite_store(tmp_path):
    store = SqliteTranscriptStore(session_dir=str(tmp_path / "sqlite"))
    yield store
    if store._conn is not None:
        store._conn.close()


@pytest.mark.parametrize("query,content", [
    ("alpha beta", "alpha only"),
    ("alpha beta", "alpha separated from beta"),
    ("alpha\nbeta", "alpha\nbeta"),
    ('"quoted"', 'a "quoted" word'),
    ("100%_done", "literal 100%_done result"),
    ("alpha beta", "exact alpha beta phrase"),
    ("missing", "unrelated content"),
    ("éclair", "ÉCLAIR"),
    (r"C:\new", r"A path C:\new"),
    ("σ", "\nΣ"),
])
def test_sqlite_matches_json_term_scoring(tmp_path, sqlite_store, query, content):
    json_store = DefaultSessionStore(session_dir=str(tmp_path / "json"))
    for store in (json_store, sqlite_store):
        assert store.add_message("reference", "user", content)
    expected = json_store.search(query)
    actual = sqlite_store.search(query)
    assert [hit.session_id for hit in actual] == [hit.session_id for hit in expected]
    assert [hit.score for hit in actual] == [hit.score for hit in expected]


def test_concurrent_searches_keep_their_own_terms(sqlite_store):
    from concurrent.futures import ThreadPoolExecutor

    store = sqlite_store
    assert store.add_message("alpha-session", "user", "alpha only")
    assert store.add_message("beta-session", "user", "beta only")
    with ThreadPoolExecutor(max_workers=2) as pool:
        searches = [pool.submit(store.search, term) for term in ("alpha", "beta") * 10]
        for index, search in enumerate(searches):
            expected = "alpha-session" if index % 2 == 0 else "beta-session"
            assert [hit.session_id for hit in search.result(timeout=5)] == [expected]


@pytest.mark.parametrize("limit", [1, 5])
def test_older_strong_match_survives_newer_partial_matches(tmp_path, sqlite_store, limit):
    json_store = DefaultSessionStore(session_dir=str(tmp_path / "json"))
    for store in (json_store, sqlite_store):
        assert store.add_message("strong", "user", "alpha beta")
        for index in range(260):
            assert store.add_message(f"newer-{index}", "user", "alpha only")
    expected = json_store.search("alpha beta", limit=limit)
    actual = sqlite_store.search("alpha beta", limit=limit)
    assert expected[0].session_id == "strong"
    assert actual[0].session_id == "strong"
    assert [hit.score for hit in actual] == [hit.score for hit in expected]


def test_search_scoring_does_not_block_session_operations(sqlite_store, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event

    store = sqlite_store
    assert store.add_message("reference", "user", "alpha beta")
    scoring = Event()
    release = Event()
    original = store._searchable_messages

    def paused_scoring(data):
        scoring.set()
        assert release.wait(5)
        return original(data)

    monkeypatch.setattr(store, "_searchable_messages", paused_scoring)
    with ThreadPoolExecutor(max_workers=3) as pool:
        search = pool.submit(store.search, "alpha beta")
        try:
            assert scoring.wait(5)
            exists = pool.submit(store.session_exists, "reference")
            write = pool.submit(store.add_message, "other", "user", "unrelated")
            assert exists.result(timeout=1)
            assert write.result(timeout=1)
        finally:
            release.set()
        assert search.result(timeout=5)[0].session_id == "reference"


@pytest.mark.parametrize("in_memory", [False, True])
def test_search_keeps_strong_match_when_concurrent_write_moves_its_order(tmp_path, monkeypatch, in_memory):
    """A row beyond the first batch must remain in this search's snapshot."""
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event

    store = SqliteTranscriptStore(session_dir=str(tmp_path), db_path=":memory:" if in_memory else None)
    try:
        assert store.add_message("strong", "user", "alpha beta")
        for index in range(260):
            assert store.add_message(f"newer-{index}", "user", "alpha only")
        expected = store.search("alpha beta", limit=300)
        scoring, release = Event(), Event()
        original = store._searchable_messages
        def paused(data):
            scoring.set()
            assert release.wait(5)
            return original(data)
        monkeypatch.setattr(store, "_searchable_messages", paused)
        with ThreadPoolExecutor(max_workers=1) as pool:
            search = pool.submit(store.search, "alpha beta", limit=300)
            try:
                assert scoring.wait(2)
                assert store.add_message("strong", "assistant", "alpha beta added later")
            finally:
                release.set()
            actual = search.result(timeout=5)
        assert [(hit.session_id, hit.score) for hit in actual] == [(hit.session_id, hit.score) for hit in expected]
        assert sum(hit.session_id == "strong" for hit in actual) == 1
    finally:
        if store._conn is not None:
            store._conn.close()


@pytest.mark.parametrize("crowding", ["lineage", "automated", "metadata"])
def test_score_and_lineage_selection_precede_result_limit(tmp_path, sqlite_store, crowding):
    json_store = DefaultSessionStore(session_dir=str(tmp_path / "json"))
    for store in (json_store, sqlite_store):
        assert store.add_message("independent", "user", "alpha" if crowding == "lineage" else "alpha beta")
        for index in range(26):
            session_id = f"newer-{index}"
            assert store.add_message(session_id, "user", "unrelated" if crowding == "metadata" else "alpha beta")
            fields = {"lineage_id": "shared"} if crowding == "lineage" else {"source": "automated"}
            if crowding == "metadata":
                fields["agent_name"] = "alpha beta"
            assert store.update_session_metadata(session_id, **fields)
    expected = json_store.search("alpha beta")
    actual = sqlite_store.search("alpha beta")
    assert "independent" in [hit.session_id for hit in expected]
    assert [hit.session_id for hit in actual] == [hit.session_id for hit in expected]
    assert [hit.score for hit in actual] == [hit.score for hit in expected]
