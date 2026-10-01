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
