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


class TestObserve:
    """Tests for the recurrence generator observe()."""

    def test_below_threshold_does_not_propose(self, engine):
        assert engine.observe("morning-brief", slots={"hour": 8}) is None
        assert engine.observe("morning-brief", slots={"hour": 8}) is None
        assert engine.pending() == []

    def test_threshold_auto_proposes(self, engine):
        assert engine.observe("morning-brief", slots={"hour": 8}) is None
        assert engine.observe("morning-brief", slots={"hour": 8}) is None
        sug_id = engine.observe("morning-brief", slots={"hour": 8})
        assert sug_id is not None
        assert sug_id.startswith("sug_")
        pending_ids = {s.id for s in engine.pending()}
        assert sug_id in pending_ids

    def test_custom_threshold(self, engine):
        sug_id = engine.observe("morning-brief", threshold=1)
        assert sug_id is not None

    def test_distinct_slots_tracked_separately(self, engine):
        # Two different intents, each observed twice — neither reaches 3.
        for _ in range(2):
            engine.observe("morning-brief", slots={"hour": 8})
            engine.observe("morning-brief", slots={"hour": 9})
        assert engine.pending() == []

    def test_default_reason_when_omitted(self, engine):
        sug_id = engine.observe("morning-brief", threshold=1)
        s = engine.get_suggestion(sug_id)
        assert "morning-brief" in s.reason

    def test_counter_resets_after_firing(self, engine):
        # First burst fires once at threshold.
        engine.observe("morning-brief", slots={"hour": 8})
        engine.observe("morning-brief", slots={"hour": 8})
        first = engine.observe("morning-brief", slots={"hour": 8})
        assert first is not None
        # Immediately after firing, the next observation is below threshold
        # again and the store dedups the identical intent, so no new suggestion.
        second = engine.observe("morning-brief", slots={"hour": 8})
        assert second is None

    def test_principal_isolation(self, engine):
        # alice recurs to threshold; bob's single observation must not ride on it.
        engine.observe("morning-brief", principal="alice")
        engine.observe("morning-brief", principal="alice")
        engine.observe("morning-brief", principal="bob")
        alice_id = engine.observe("morning-brief", principal="alice")
        assert alice_id is not None
        assert {s.id for s in engine.pending("bob")} == set()


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
