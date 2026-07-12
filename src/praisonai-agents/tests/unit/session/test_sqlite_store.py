"""Tests for indexed cross-session recall (Issue #2927).

Covers:
- SqliteSessionStore FTS5-backed search returns anchored hits.
- Anchored discovery bookends (opening/closing) in SessionHit.
- Automated (high-volume) session demotion in ranking.
- Lineage-aware dedup collapsing reset/compacted continuations.
"""

import tempfile

import pytest

from praisonaiagents.session.store import DefaultSessionStore
from praisonaiagents.session import SqliteSessionStore


@pytest.fixture
def tmp_dir():
    with tempfile.TemporaryDirectory() as d:
        yield d


def _seed(store, session_id, messages, **top):
    from praisonaiagents.session.store import SessionData, SessionMessage

    session = SessionData(session_id=session_id)
    for role, content in messages:
        session.messages.append(SessionMessage(role=role, content=content))
    for k, v in top.items():
        setattr(session, k, v) if hasattr(session, k) else session.metadata.update({k: v})
    store._save_session(session)


class TestSqliteSessionStore:
    def test_import_and_construct(self, tmp_dir):
        store = SqliteSessionStore(session_dir=tmp_dir, db_path=":memory:")
        assert isinstance(store, DefaultSessionStore)

    def test_search_finds_session(self, tmp_dir):
        store = SqliteSessionStore(session_dir=tmp_dir)
        store.add_message("s1", "user", "Please help with the billing migration")
        store.add_message("s1", "assistant", "Sure, migrating billing now")
        store.add_message("s2", "user", "unrelated weather chat")

        hits = store.search("billing migration")
        assert len(hits) == 1
        assert hits[0].session_id == "s1"

    def test_search_backfills_existing_json(self, tmp_dir):
        # Write via a plain store first (no index), then open sqlite store.
        plain = DefaultSessionStore(session_dir=tmp_dir)
        plain.add_message("old", "user", "legacy topic about kubernetes")

        store = SqliteSessionStore(session_dir=tmp_dir)
        hits = store.search("kubernetes")
        assert any(h.session_id == "old" for h in hits)

    def test_anchored_bookends(self, tmp_dir):
        store = SqliteSessionStore(session_dir=tmp_dir)
        msgs = [
            ("user", "Goal: fix the deploy pipeline"),
            ("assistant", "Looking into the pipeline"),
            ("user", "the special keyword marker is here"),
            ("assistant", "Found the issue"),
            ("user", "Great, resolved now"),
        ]
        for role, content in msgs:
            store.add_message("b1", role, content)

        hits = store.search("keyword marker")
        assert hits
        bookends = hits[0].bookends
        assert bookends.get("opening")
        assert "Goal" in bookends["opening"][0]["content"]
        assert bookends.get("closing")
        assert "resolved" in bookends["closing"][-1]["content"]

    def test_delete_removes_from_index(self, tmp_dir):
        store = SqliteSessionStore(session_dir=tmp_dir)
        store.add_message("d1", "user", "quantum entanglement notes")
        assert store.search("quantum")
        store.delete_session("d1")
        assert not store.search("quantum")

    def test_partial_index_still_backfills_legacy_json(self, tmp_dir):
        # Legacy JSON written before any indexing.
        plain = DefaultSessionStore(session_dir=tmp_dir)
        plain.add_message("legacy", "user", "legacy topic about terraform")

        store = SqliteSessionStore(session_dir=tmp_dir)
        # Index a brand-new session first -> index is now non-empty. A COUNT==0
        # backfill guard would permanently skip the legacy JSON.
        store.add_message("fresh", "user", "brand new terraform note")

        hits = store.search("terraform")
        ids = {h.session_id for h in hits}
        assert "legacy" in ids
        assert "fresh" in ids

    def test_transcript_replacement_refreshes_index(self, tmp_dir):
        store = SqliteSessionStore(session_dir=tmp_dir)
        store.add_message("r1", "user", "original content about pelicans")
        assert store.search("pelicans")

        # Replace the whole transcript via set_chat_history (goes through
        # _modify_session_locked, NOT _save_session).
        store.set_chat_history(
            "r1", [{"role": "user", "content": "replaced content about narwhals"}]
        )
        # Stale term must be gone; new term must be found.
        assert not store.search("pelicans")
        assert store.search("narwhals")

    def test_sibling_sessions_not_over_deduped(self, tmp_dir):
        store = SqliteSessionStore(session_dir=tmp_dir)
        # Two independent children forked from the same parent -> distinct
        # conversations, must both surface (parent_session_id is not a chain id).
        _seed(
            store,
            "childA",
            [("user", "sibling recall topic alpha branch")],
            parent_session_id="P1",
        )
        _seed(
            store,
            "childB",
            [("user", "sibling recall topic beta branch")],
            parent_session_id="P1",
        )
        hits = store.search("sibling recall topic")
        ids = {h.session_id for h in hits}
        assert ids == {"childA", "childB"}


class TestDefaultStoreSearchEnhancements:
    def test_bookends_present(self, tmp_dir):
        store = DefaultSessionStore(session_dir=tmp_dir)
        for role, content in [
            ("user", "opening goal about invoices"),
            ("assistant", "ok"),
            ("user", "the invoices magic-token detail"),
            ("assistant", "done"),
            ("user", "closing outcome invoices"),
        ]:
            store.add_message("x1", role, content)
        hits = store.search("magic-token")
        assert hits
        assert hits[0].bookends.get("opening")

    def test_automated_session_demoted(self, tmp_dir):
        store = DefaultSessionStore(session_dir=tmp_dir)
        # Interactive session with the term once.
        store.add_message("human", "user", "need the report summary")
        # Automated/scheduled session tagged as such, also contains the term.
        _seed(
            store,
            "cron",
            [("assistant", "scheduled report summary run")],
            source="scheduled",
        )
        hits = store.search("report summary")
        ids = [h.session_id for h in hits]
        assert ids[0] == "human"

    def test_lineage_dedup(self, tmp_dir):
        store = DefaultSessionStore(session_dir=tmp_dir)
        _seed(
            store,
            "root",
            [("user", "migration lineage topic root")],
            lineage_id="L1",
        )
        _seed(
            store,
            "continuation",
            [("user", "migration lineage topic continued")],
            lineage_id="L1",
        )
        hits = store.search("lineage topic")
        # Both belong to lineage L1 -> collapse to a single hit.
        assert len(hits) == 1

    def test_backward_compatible_hit_dict(self, tmp_dir):
        store = DefaultSessionStore(session_dir=tmp_dir)
        store.add_message("c1", "user", "hello world unique-term")
        hits = store.search("unique-term")
        d = hits[0].as_dict()
        assert d["session_id"] == "c1"
        assert "messages" in d
