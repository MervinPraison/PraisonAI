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
