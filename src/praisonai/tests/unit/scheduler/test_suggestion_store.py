"""Tests for SuggestionStore."""

import json
import os
import tempfile
import threading
import time
from pathlib import Path

import pytest

from praisonaiagents.scheduler.suggestion_store import (
    SuggestionStore,
    Suggestion,
    MAX_PENDING_CAP,
    DEDUP_WINDOW_SEC,
)


@pytest.fixture
def tmp_store():
    """Create a SuggestionStore backed by a temporary file."""
    with tempfile.TemporaryDirectory() as tmpdir:
        path = str(Path(tmpdir) / "suggestions.json")
        store = SuggestionStore(path=path)
        yield store


@pytest.fixture
def sample():
    """A sample suggestion for tests."""
    return Suggestion(
        id="sug_test001",
        blueprint_name="morning-brief",
        slots={"hour": 8, "weekdays": "mon-fri"},
        deliver="telegram",
        reason="Test suggestion",
    )


class TestSuggestionStoreBasics:
    """Basic CRUD operations."""

    def test_add_and_get(self, tmp_store, sample):
        ok = tmp_store.add(sample)
        assert ok is True
        retrieved = tmp_store.get("sug_test001")
        assert retrieved is not None
        assert retrieved.blueprint_name == "morning-brief"
        assert retrieved.reason == "Test suggestion"

    def test_get_missing(self, tmp_store):
        assert tmp_store.get("nonexistent") is None

    def test_list_pending_empty(self, tmp_store):
        pending = tmp_store.list_pending()
        assert pending == []

    def test_list_pending_with_suggestion(self, tmp_store, sample):
        tmp_store.add(sample)
        pending = tmp_store.list_pending()
        assert len(pending) == 1
        assert pending[0].id == "sug_test001"

    def test_list_pending_excludes_dismissed(self, tmp_store, sample):
        tmp_store.add(sample)
        tmp_store.dismiss("sug_test001")
        pending = tmp_store.list_pending()
        assert len(pending) == 0

    def test_list_pending_excludes_accepted(self, tmp_store, sample):
        tmp_store.add(sample)
        tmp_store.accept("sug_test001")
        pending = tmp_store.list_pending()
        assert len(pending) == 0


class TestAcceptDismiss:
    """Tests for accept() and dismiss()."""

    def test_accept(self, tmp_store, sample):
        tmp_store.add(sample)
        ok = tmp_store.accept("sug_test001")
        assert ok is True
        s = tmp_store.get("sug_test001")
        assert s.accepted is True

    def test_accept_missing(self, tmp_store):
        ok = tmp_store.accept("nonexistent")
        assert ok is False

    def test_dismiss(self, tmp_store, sample):
        tmp_store.add(sample)
        ok = tmp_store.dismiss("sug_test001")
        assert ok is True
        s = tmp_store.get("sug_test001")
        assert s.dismissed is True

    def test_dismiss_missing(self, tmp_store):
        ok = tmp_store.dismiss("nonexistent")
        assert ok is False


class TestCap:
    """Tests for the MAX_PENDING_CAP enforcement."""

    def test_add_respects_cap(self, tmp_store):
        for i in range(MAX_PENDING_CAP):
            s = Suggestion(
                id=f"sug_{i:04d}",
                blueprint_name="morning-brief",
                slots={"hour": i % 24},
            )
            ok = tmp_store.add(s)
            assert ok is True

        # One more should fail
        extra = Suggestion(
            id="sug_extra",
            blueprint_name="weekly-review",
            slots={"hour": 17},
        )
        ok = tmp_store.add(extra)
        assert ok is False

    def test_cap_does_not_count_dismissed(self, tmp_store):
        # Fill to cap
        for i in range(MAX_PENDING_CAP):
            s = Suggestion(
                id=f"sug_{i:04d}",
                blueprint_name="morning-brief",
                slots={"hour": i % 24},
            )
            tmp_store.add(s)

        # Dismiss one, freeing a slot
        tmp_store.dismiss("sug_0000")

        extra = Suggestion(
            id="sug_extra",
            blueprint_name="weekly-review",
            slots={"hour": 17},
        )
        ok = tmp_store.add(extra)
        assert ok is True


class TestDedup:
    """Tests for dedup within the window."""

    def test_duplicate_within_window_is_rejected(self, tmp_store):
        s1 = Suggestion(
            id="sug_a",
            blueprint_name="morning-brief",
            slots={"hour": 8},
        )
        ok = tmp_store.add(s1)
        assert ok is True

        s2 = Suggestion(
            id="sug_b",
            blueprint_name="morning-brief",
            slots={"hour": 8},
        )
        ok = tmp_store.add(s2)
        assert ok is False  # deduped

    def test_different_slots_allowed(self, tmp_store):
        s1 = Suggestion(
            id="sug_a",
            blueprint_name="morning-brief",
            slots={"hour": 8},
        )
        tmp_store.add(s1)

        s2 = Suggestion(
            id="sug_b",
            blueprint_name="morning-brief",
            slots={"hour": 9},
        )
        ok = tmp_store.add(s2)
        assert ok is True  # different slots

    def test_different_blueprint_allowed(self, tmp_store):
        s1 = Suggestion(
            id="sug_a",
            blueprint_name="morning-brief",
            slots={"hour": 8},
        )
        tmp_store.add(s1)

        s2 = Suggestion(
            id="sug_b",
            blueprint_name="important-mail",
            slots={"hour": 8},
        )
        ok = tmp_store.add(s2)
        assert ok is True  # different blueprint


class TestExpiry:
    """Tests for expiry-related behavior."""

    def test_expired_not_in_pending(self, tmp_store):
        past = Suggestion(
            id="sug_expired",
            blueprint_name="morning-brief",
            created_at=time.time() - 10000,
            expires_at=time.time() - 1,  # already expired
        )
        tmp_store.add(past)
        pending = tmp_store.list_pending()
        # The expired suggestion should not appear
        ids = {s.id for s in pending}
        assert "sug_expired" not in ids

    def test_non_expired_in_pending(self, tmp_store):
        future = Suggestion(
            id="sug_future",
            blueprint_name="morning-brief",
            expires_at=time.time() + 3600,  # expires in 1 hour
        )
        tmp_store.add(future)
        pending = tmp_store.list_pending()
        ids = {s.id for s in pending}
        assert "sug_future" in ids

    def test_no_expiry_always_in_pending(self, tmp_store):
        noexp = Suggestion(
            id="sug_noexp",
            blueprint_name="morning-brief",
            expires_at=0.0,  # no expiry
        )
        # Directly manipulate created_at to simulate old suggestion
        noexp.created_at = time.time() - 100000
        tmp_store.add(noexp)
        pending = tmp_store.list_pending()
        ids = {s.id for s in pending}
        assert "sug_noexp" in ids

    def test_prune_expired_removes_old_suggestions(self, tmp_store):
        expired = Suggestion(
            id="sug_old",
            blueprint_name="test",
            expires_at=time.time() - 1,  # expired
        )
        valid = Suggestion(
            id="sug_new",
            blueprint_name="test",
            expires_at=time.time() + 3600,  # still valid
        )
        tmp_store.add(expired)
        tmp_store.add(valid)

        count = tmp_store.prune_expired()
        assert count >= 1
        assert tmp_store.get("sug_old") is None
        assert tmp_store.get("sug_new") is not None


class TestPersistence:
    """Tests that suggestions survive across store instances."""

    def test_persistence_across_instances(self, tmp_store, sample):
        tmp_store.add(sample)

        # Create a new store pointing to the same file
        store2 = SuggestionStore(path=tmp_store._path)
        retrieved = store2.get("sug_test001")
        assert retrieved is not None
        assert retrieved.blueprint_name == "morning-brief"
        assert retrieved.slots == {"hour": 8, "weekdays": "mon-fri"}


class TestThreadSafety:
    """Tests that concurrent access does not corrupt state."""

    def test_concurrent_adds(self, tmp_store):
        errors = []

        def add_one(i):
            try:
                s = Suggestion(
                    id=f"thread_{i}",
                    blueprint_name="test",
                    slots={"index": i},  # unique slots per thread
                )
                tmp_store.add(s)
            except Exception as e:
                errors.append(e)

        threads = [
            threading.Thread(target=add_one, args=(i,))
            for i in range(50)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors
        pending = tmp_store.list_pending()
        # Under concurrent load the cap may or may not be reached exactly,
        # but we should have at least 1 and at most MAX_PENDING_CAP
        assert 1 <= len(pending) <= MAX_PENDING_CAP
