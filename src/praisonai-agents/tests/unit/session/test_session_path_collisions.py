"""Distinct session ids must never share a session file (Issue #6024)."""

import json
import os

import pytest

from praisonaiagents.session.store import DefaultSessionStore


@pytest.fixture
def store(tmp_path):
    return DefaultSessionStore(session_dir=str(tmp_path))


@pytest.mark.parametrize("a,b", [
    ("alice.smith", "alice_smith"),
    ("a:b", "a_b"),
    ("bot_email_alice.smith@example.com", "bot_email_alice_smith@example.com"),
    ("u+tag@x.com", "u_tag_x_com"),
    ("a/b", "a b"),
    ("telegram:acct:default:chat:-1001:", "telegram_acct_default_chat_-1001_"),
])
def test_colliding_ids_get_distinct_paths(store, a, b):
    assert store._get_session_path(a) != store._get_session_path(b)


def test_safe_ids_keep_legacy_filename(store):
    sid = "user_123-abc" + "x" * 100
    assert os.path.basename(store._get_session_path(sid)) == f"{sid}.json"


def test_colliding_users_have_separate_histories(store):
    store.add_user_message("alice.smith@example.com", "My PIN is 4471.")
    assert store.get_chat_history("alice_smith@example.com") == []
    store.add_user_message("alice_smith@example.com", "hello")
    assert [m["content"] for m in store.get_chat_history("alice.smith@example.com")] == ["My PIN is 4471."]
    assert [m["content"] for m in store.get_chat_history("alice_smith@example.com")] == ["hello"]


def _write_legacy(store, stem, owner, content):
    path = os.path.join(store.session_dir, f"{stem}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"session_id": owner, "messages": [
            {"role": "user", "content": content, "timestamp": 1.0}]}, f)
    return path


def test_legacy_file_migrated_only_for_owner(store):
    legacy = _write_legacy(store, "alice_smith", "alice.smith", "secret")
    # A colliding unsafe id never adopts it.
    assert store.get_chat_history("alice:smith") == []
    assert os.path.exists(legacy)
    # The real owner migrates it on first read.
    assert [m["content"] for m in store.get_chat_history("alice.smith")] == ["secret"]
    assert not os.path.exists(legacy)


def test_foreign_file_never_served_and_not_destroyed(store):
    # Safe id whose filename holds another id's unmigrated legacy transcript.
    _write_legacy(store, "alice_smith", "alice.smith", "secret")
    assert store.get_chat_history("alice_smith") == []
    store.add_user_message("alice_smith", "mine")
    assert [m["content"] for m in store.get_chat_history("alice_smith")] == ["mine"]
    # The owner's history was relocated rather than overwritten.
    assert [m["content"] for m in store.get_chat_history("alice.smith")] == ["secret"]


def test_failed_foreign_move_aborts_write(store, monkeypatch, tmp_path):
    monkeypatch.setattr(store, "_spill_dir", lambda: str(tmp_path / "spill"))
    store.add_user_message("alice.smith", "new")  # owner path taken
    legacy = _write_legacy(store, "alice_smith", "alice.smith", "secret")
    monkeypatch.setattr(store, "_quarantine_corrupt", lambda p: None)
    assert store.add_user_message("alice_smith", "mine") is False
    with open(legacy, encoding="utf-8") as f:
        assert json.load(f)["session_id"] == "alice.smith"


def test_foreign_file_set_aside_when_owner_path_taken(store):
    store.add_user_message("alice.smith", "new")
    legacy = _write_legacy(store, "alice_smith", "alice.smith", "secret")
    store.add_user_message("alice_smith", "mine")
    assert [m["content"] for m in store.get_chat_history("alice_smith")] == ["mine"]
    assert [m["content"] for m in store.get_chat_history("alice.smith")] == ["new"]
    aside = [p for p in os.listdir(store.session_dir) if p.startswith("alice_smith.json.corrupt-")]
    assert len(aside) == 1 and os.path.exists(legacy)


def test_sqlite_backfill_indexes_hashed_filenames(tmp_path):
    from praisonaiagents.session.sqlite_store import SqliteSessionStore

    DefaultSessionStore(session_dir=str(tmp_path)).add_user_message(
        "alice.smith@example.com", "narwhal record")
    store = SqliteSessionStore(session_dir=str(tmp_path), db_path=":memory:")
    assert [h.session_id for h in store.search("narwhal")] == ["alice.smith@example.com"]


def test_sqlite_backfill_indexes_legacy_collision_files(tmp_path):
    from praisonaiagents.session.sqlite_store import SqliteSessionStore

    legacy = DefaultSessionStore(session_dir=str(tmp_path))
    _write_legacy(legacy, "alice_smith", "alice.smith", "walrus record")
    store = SqliteSessionStore(session_dir=str(tmp_path), db_path=":memory:")
    assert [h.session_id for h in store.search("walrus")] == ["alice.smith"]


def test_spill_recovery_does_not_wait_on_own_lock(store, monkeypatch, tmp_path):
    import time

    spill = tmp_path / "spill"
    spill.mkdir()
    monkeypatch.setattr(store, "_spill_dir", lambda: str(spill))
    # Legacy name of "alice.smith" belongs to another id, so it is never migrated.
    _write_legacy(store, "alice_smith", "alice:smith", "theirs")
    (spill / "alice_smith.1.json").write_text(json.dumps({"session_id": "alice.smith", "messages": [
        {"role": "user", "content": "spilled", "timestamp": 2.0}]}), encoding="utf-8")
    start = time.monotonic()
    assert [m["content"] for m in store.get_chat_history("alice.smith")] == ["spilled"]
    assert time.monotonic() - start < store.lock_timeout
