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
        for index in range(26):
            assert store.add_message(f"newer-{index}", "user", "alpha only")
    expected = json_store.search("alpha beta", limit=limit)
    actual = sqlite_store.search("alpha beta", limit=limit)
    assert expected[0].session_id == "strong"
    assert actual[0].session_id == "strong"
    assert [hit.score for hit in actual] == [hit.score for hit in expected]


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
