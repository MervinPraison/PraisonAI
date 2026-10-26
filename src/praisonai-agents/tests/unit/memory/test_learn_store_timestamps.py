from datetime import datetime, timezone

from praisonaiagents.memory.learn.stores import InsightStore, LearnEntry


def test_new_entry_timestamps_are_timezone_aware():
    entry = LearnEntry(id="e1", content="hello")
    assert datetime.fromisoformat(entry.created_at).tzinfo is not None
    assert datetime.fromisoformat(entry.updated_at).tzinfo is not None


def test_prune_handles_legacy_naive_timestamps(tmp_path):
    store = InsightStore(store_path=str(tmp_path / "store.json"), retention_days=1)
    now = datetime.now(timezone.utc)

    # An entry persisted before the timezone-aware change: naive isoformat, no offset.
    legacy = LearnEntry(
        id="old",
        content="old",
        created_at="2020-01-01T00:00:00",
        updated_at="2020-01-01T00:00:00",
    )
    # Must not raise "can't subtract offset-naive and offset-aware datetimes".
    assert store._is_stale(legacy, now) is True

    fresh = LearnEntry(id="new", content="new")
    assert store._is_stale(fresh, now) is False
