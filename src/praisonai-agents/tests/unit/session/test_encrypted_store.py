"""Session transcripts can be encrypted at rest.

Conversation history was written to disk in plaintext and nothing in the package
imported a cryptography primitive, which ruled PraisonAI out wherever the
transcript is regulated data.
"""
import json
import pytest

from praisonaiagents.session.encrypted_store import (
    EncryptedSessionStore,
    SessionEncryptionError,
    generate_session_key,
)


class FakeStore:
    """Stands in for any session store; records exactly what was handed to it."""

    def __init__(self):
        self.rows = []

    def add_message(self, session_id, role, content, metadata=None):
        self.rows.append({"session_id": session_id, "role": role,
                          "content": content, "metadata": metadata})
        return True

    def get_chat_history(self, session_id, max_messages=None):
        rows = [r for r in self.rows if r["session_id"] == session_id]
        return rows[-max_messages:] if max_messages else rows

    def session_exists(self, session_id):
        return any(r["session_id"] == session_id for r in self.rows)


SECRET = "my card is 4111 1111 1111 1111"


@pytest.fixture
def key():
    return generate_session_key()


class TestAtRest:
    def test_the_stored_content_is_not_the_plaintext(self, key):
        inner = FakeStore()
        EncryptedSessionStore(inner, key=key).add_message("s1", "user", SECRET)
        stored = inner.rows[0]["content"]
        assert SECRET not in stored
        assert "4111" not in stored
        assert stored.startswith(EncryptedSessionStore.PREFIX)

    def test_control_an_unwrapped_store_writes_plaintext(self):
        """The control: this is what the wrapper exists to change."""
        inner = FakeStore()
        inner.add_message("s1", "user", SECRET)
        assert inner.rows[0]["content"] == SECRET

    def test_metadata_is_encrypted_too(self, key):
        inner = FakeStore()
        EncryptedSessionStore(inner, key=key).add_message(
            "s1", "user", "hi", metadata={"patient": "Alice"}
        )
        assert "Alice" not in json.dumps(inner.rows[0]["metadata"])

    def test_ids_and_roles_stay_readable_because_the_store_indexes_on_them(self, key):
        inner = FakeStore()
        EncryptedSessionStore(inner, key=key).add_message("s1", "user", SECRET)
        assert inner.rows[0]["session_id"] == "s1"
        assert inner.rows[0]["role"] == "user"


class TestRoundTrip:
    def test_reading_back_returns_the_original(self, key):
        store = EncryptedSessionStore(FakeStore(), key=key)
        store.add_message("s1", "user", SECRET)
        assert store.get_chat_history("s1")[0]["content"] == SECRET

    def test_metadata_round_trips(self, key):
        store = EncryptedSessionStore(FakeStore(), key=key)
        store.add_message("s1", "user", "hi", metadata={"patient": "Alice"})
        assert store.get_chat_history("s1")[0]["metadata"] == {"patient": "Alice"}

    def test_the_wrong_key_fails_loudly_rather_than_returning_gibberish(self, key):
        inner = FakeStore()
        EncryptedSessionStore(inner, key=key).add_message("s1", "user", SECRET)
        other = EncryptedSessionStore(inner, key=generate_session_key())
        with pytest.raises(SessionEncryptionError, match="does not match"):
            other.get_chat_history("s1")

    def test_history_written_before_encryption_is_still_readable(self, key):
        """Switching this on must not make existing transcripts unreadable."""
        inner = FakeStore()
        inner.add_message("s1", "user", "written in plaintext")
        assert EncryptedSessionStore(inner, key=key).get_chat_history("s1")[0][
            "content"
        ] == "written in plaintext"


class TestHonestLimits:
    def test_search_raises_instead_of_returning_an_empty_list(self, key):
        """'No results' and 'search cannot work here' mean opposite things."""
        store = EncryptedSessionStore(FakeStore(), key=key)
        store.add_message("s1", "user", SECRET)
        with pytest.raises(SessionEncryptionError, match="ciphertext"):
            store.search("4111")

    def test_an_empty_key_is_refused(self):
        with pytest.raises(SessionEncryptionError, match="key is required"):
            EncryptedSessionStore(FakeStore(), key="")

    def test_a_malformed_key_is_refused(self):
        with pytest.raises(SessionEncryptionError, match="not a valid Fernet key"):
            EncryptedSessionStore(FakeStore(), key="not-a-real-key")

    def test_unwrapped_methods_are_forwarded(self, key):
        """Wrapping must not silently drop capabilities the inner store has."""
        store = EncryptedSessionStore(FakeStore(), key=key)
        store.add_message("s1", "user", "hi")
        assert store.session_exists("s1") is True


class TestAgainstTheRealStore:
    """The claim that matters is about bytes on disk, not about a fake."""

    def test_plaintext_never_reaches_the_filesystem(self, key, tmp_path):
        from praisonaiagents.session.sqlite_store import SqliteSessionStore

        store = EncryptedSessionStore(SqliteSessionStore(str(tmp_path)), key=key)
        store.add_message("s1", "user", SECRET)

        blobs = b"".join(p.read_bytes() for p in tmp_path.rglob("*") if p.is_file())
        assert b"4111 1111 1111 1111" not in blobs
        assert EncryptedSessionStore.PREFIX.encode() in blobs
        assert store.get_chat_history("s1")[0]["content"] == SECRET

    def test_control_the_same_store_unwrapped_leaves_plaintext_on_disk(self, tmp_path):
        from praisonaiagents.session.sqlite_store import SqliteSessionStore

        SqliteSessionStore(str(tmp_path)).add_message("s1", "user", SECRET)
        blobs = b"".join(p.read_bytes() for p in tmp_path.rglob("*") if p.is_file())
        assert b"4111 1111 1111 1111" in blobs
