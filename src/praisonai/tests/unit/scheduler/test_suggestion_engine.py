"""Tests for SuggestionEngine."""

import tempfile
from pathlib import Path

import pytest

from praisonai.scheduler.suggestion_engine import SuggestionEngine
from praisonaiagents.scheduler.suggestion_store import MAX_PENDING_CAP


def _make_engine(tmpdir: str) -> SuggestionEngine:
    """Create a SuggestionEngine backed by a temp file."""
    path = str(Path(tmpdir) / "suggestions.json")
    return SuggestionEngine(store_path=path)


@pytest.fixture
def engine():
    """Create an isolated SuggestionEngine for each test."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield _make_engine(tmpdir)


class TestPropose:
    """Tests for propose()."""

    def test_propose_returns_id(self, engine):
        sug_id = engine.propose(
            "morning-brief",
            slots={"hour": 8},
            reason="Test proposal",
        )
        assert sug_id is not None
        assert sug_id.startswith("sug_")

    def test_propose_is_in_pending(self, engine):
        sug_id = engine.propose("morning-brief", reason="Test")
        pending = engine.pending()
        ids = {s.id for s in pending}
        assert sug_id in ids

    def test_propose_different_slots(self, engine):
        id1 = engine.propose("morning-brief", slots={"hour": 8})
        id2 = engine.propose("morning-brief", slots={"hour": 9})
        assert id1 is not None
        assert id2 is not None
        assert id1 != id2

    def test_propose_duplicate_is_rejected(self, engine):
        id1 = engine.propose("morning-brief", slots={"hour": 8})
        id2 = engine.propose("morning-brief", slots={"hour": 8})
        assert id1 is not None
        assert id2 is None  # duplicate

    def test_propose_cap(self, engine):
        for i in range(MAX_PENDING_CAP):
            sug_id = engine.propose(
                "morning-brief",
                slots={"hour": i % 24},
                reason=f"Proposal {i}",
            )
            assert sug_id is not None

        # One more should be rejected
        extra = engine.propose("weekly-review", slots={"hour": 17})
        assert extra is None

    def test_propose_negative_ttl_rejected(self, engine):
        """Negative ttl_seconds must raise (0 means no expiry)."""
        with pytest.raises(ValueError):
            engine.propose("morning-brief", slots={"hour": 8}, ttl_seconds=-1)

    def test_propose_zero_ttl_no_expiry(self, engine):
        """ttl_seconds=0 means no expiry (expires_at == 0)."""
        sug_id = engine.propose("morning-brief", slots={"hour": 8}, ttl_seconds=0)
        sug = engine.get_suggestion(sug_id)
        assert sug.expires_at == 0.0

    def test_propose_copies_slots(self, engine):
        """Mutating the caller's slots dict must not affect the stored suggestion."""
        slots = {"hour": 8}
        sug_id = engine.propose("morning-brief", slots=slots)
        slots["hour"] = 99
        sug = engine.get_suggestion(sug_id)
        assert sug.slots["hour"] == 8


class TestAcceptDismiss:
    """Tests for accept() and dismiss()."""

    def test_accept(self, engine):
        sug_id = engine.propose("morning-brief", reason="test")
        ok = engine.accept(sug_id)
        assert ok is True
        pending_ids = {s.id for s in engine.pending()}
        assert sug_id not in pending_ids

    def test_accept_missing(self, engine):
        ok = engine.accept("nonexistent")
        assert ok is False

    def test_dismiss(self, engine):
        sug_id = engine.propose("morning-brief", reason="test")
        ok = engine.dismiss(sug_id)
        assert ok is True
        pending_ids = {s.id for s in engine.pending()}
        assert sug_id not in pending_ids

    def test_get_suggestion(self, engine):
        sug_id = engine.propose("morning-brief", reason="test")
        s = engine.get_suggestion(sug_id)
        assert s is not None
        assert s.blueprint_name == "morning-brief"

    def test_get_suggestion_missing(self, engine):
        assert engine.get_suggestion("nonexistent") is None


class TestPending:
    """Tests for pending()."""

    def test_pending_empty_initially(self, engine):
        assert engine.pending() == []

    def test_pending_respects_dismiss(self, engine):
        id1 = engine.propose("morning-brief", reason="keep")
        id2 = engine.propose("important-mail", reason="dismiss me")
        engine.dismiss(id2)
        pending = engine.pending()
        pending_ids = {s.id for s in pending}
        assert id1 in pending_ids
        assert id2 not in pending_ids

    def test_pending_respects_accept(self, engine):
        id1 = engine.propose("morning-brief", reason="keep")
        id2 = engine.propose("important-mail", reason="accept me")
        engine.accept(id2)
        pending = engine.pending()
        pending_ids = {s.id for s in pending}
        assert id1 in pending_ids
        assert id2 not in pending_ids
