from datetime import datetime, timezone

from praisonaiagents.memory.learn.stores import InsightStore, LearnEntry


def test_new_entry_timestamps_are_timezone_aware():
    """New learn entries carry timezone-aware created_at and updated_at."""
    entry = LearnEntry(id="e1", content="hello")
    assert datetime.fromisoformat(entry.created_at).tzinfo is not None
    assert datetime.fromisoformat(entry.updated_at).tzinfo is not None


def test_prune_handles_legacy_naive_timestamps(tmp_path):
    """Pruning treats legacy naive timestamps as UTC instead of raising on the subtraction."""
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


def test_prune_evicts_stale_legacy_entry_end_to_end(tmp_path):
    """prune() archives a stale legacy (naive-timestamp) entry without raising."""
    store = InsightStore(store_path=str(tmp_path / "store.json"), retention_days=1)
    store._entries["old"] = LearnEntry(
        id="old",
        content="old",
        created_at="2020-01-01T00:00:00",
        updated_at="2020-01-01T00:00:00",
    )

    assert store.prune(save=False) == 1
    assert "old" not in store._entries


def test_list_all_orders_by_instant_not_raw_string(tmp_path):
    """list_all() orders by the actual UTC instant, even when offsets differ.

    00:30+01:00 is an earlier instant than 00:00+00:00, but a raw-string sort
    would order them the other way round.
    """
    store = InsightStore(store_path=str(tmp_path / "store.json"))
    store._entries = {
        "earlier": LearnEntry(id="earlier", content="e", updated_at="2024-01-01T00:30:00+01:00"),
        "later": LearnEntry(id="later", content="l", updated_at="2024-01-01T00:00:00+00:00"),
    }
    store._save()  # persist so list_all's refresh reloads these entries

    ordered = [e.id for e in store.list_all()]  # reverse=True: most recent first
    assert ordered == ["later", "earlier"]


def test_prune_evicts_never_used_entry_before_used_one(tmp_path):
    """At equal use_count, a never-used entry (last_used=None) is evicted first."""
    store = InsightStore(store_path=str(tmp_path / "store.json"), max_entries=1)
    store._entries = {
        "never": LearnEntry(
            id="never", content="n", use_count=0, last_used=None,
            created_at="2024-01-01T00:00:00+00:00",
        ),
        "used": LearnEntry(
            id="used", content="u", use_count=0,
            last_used="2024-06-01T00:00:00+00:00",
            created_at="2024-01-01T00:00:00+00:00",
        ),
    }

    store.prune(save=False)
    assert "never" not in store._entries
    assert "used" in store._entries
