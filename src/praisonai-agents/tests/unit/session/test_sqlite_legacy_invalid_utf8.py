"""Legacy migration must isolate malformed files from valid transcripts."""

import pytest

from praisonaiagents.session import SqliteTranscriptStore
from praisonaiagents.session.store import DefaultSessionStore


@pytest.mark.parametrize("bad_first", [True, False])
def test_invalid_utf8_does_not_interrupt_legacy_migration(tmp_path, monkeypatch, bad_first):
    import praisonaiagents.session.sqlite_transcript_store as module

    legacy = DefaultSessionStore(session_dir=str(tmp_path))
    assert legacy.add_message("valid", "user", "preserve this history")
    bad = tmp_path / "invalid.json"
    payload = b"\xff\xfe"
    bad.write_bytes(payload)
    valid = "valid.json"
    names = [bad.name, valid] if bad_first else [valid, bad.name]
    original = module.os.listdir

    def ordered(path):
        if str(path) == str(tmp_path):
            return names
        return original(path)

    monkeypatch.setattr(module.os, "listdir", ordered)
    store = SqliteTranscriptStore(session_dir=str(tmp_path))
    reopened = None
    try:
        assert store.session_exists("valid")
        assert store.get_chat_history("valid") == [
            {"role": "user", "content": "preserve this history"},
        ]
        reopened = SqliteTranscriptStore(session_dir=str(tmp_path))
        assert reopened.get_chat_history("valid") == store.get_chat_history("valid")
        assert bad.read_bytes() == payload
        assert not store.session_exists("invalid")
    finally:
        for current in (store, reopened):
            if current is not None and current._conn is not None:
                current._conn.close()
