"""Encrypt session transcripts at rest.

Conversation history lands on disk in plaintext: `sqlite_store.py` and
`sqlite_transcript_store.py` write message content as-is, and nothing in this
package imports a cryptography primitive. That rules PraisonAI out anywhere the
transcript is regulated data, which is most places a support or clinical agent
would run.

This wraps ANY session store rather than adding another one, so encryption is a
decision about deployment instead of a fork of the storage layer:

    from praisonaiagents.session import SqliteSessionStore, EncryptedSessionStore

    store = EncryptedSessionStore(SqliteSessionStore(path), key=os.environ["PRAISONAI_SESSION_KEY"])
    store.add_message("s1", "user", "my card is 4111 1111 1111 1111")
    # on disk: gAAAAABm... ; in memory: the original text

What it does NOT do, stated plainly rather than discovered later:

* **Search cannot see through encryption.** `search()` matches ciphertext, so a
  substring query finds nothing. It raises rather than returning a confident
  empty list, because "no results" and "search is impossible here" mean opposite
  things and the empty list is the more dangerous answer.
* **Only content and metadata are encrypted.** Session ids, roles and timestamps
  stay readable, because the store indexes and orders by them. Anyone treating
  ids as sensitive needs a different design, not this wrapper.
* **Losing the key loses the transcripts.** There is no recovery path, by
  design.
"""

import json
from typing import Any, Dict, List, Optional

__all__ = ["EncryptedSessionStore", "SessionEncryptionError", "generate_session_key"]


class SessionEncryptionError(RuntimeError):
    """Raised when encryption cannot be performed or undone."""


def _load_fernet():
    try:
        from cryptography.fernet import Fernet, InvalidToken  # noqa: F401
        return Fernet, InvalidToken
    except ImportError as exc:  # pragma: no cover - environment dependent
        raise SessionEncryptionError(
            "Encrypting sessions needs the `cryptography` package. "
            "Install it with: pip install cryptography"
        ) from exc


def generate_session_key() -> str:
    """A new key, suitable for PRAISONAI_SESSION_KEY. Store it somewhere safe."""
    Fernet, _ = _load_fernet()
    return Fernet.generate_key().decode("ascii")


class EncryptedSessionStore:
    """Encrypt message content and metadata before they reach the wrapped store.

    Every method not named here is forwarded untouched, so wrapping a store does
    not silently drop capabilities it has and this one has not heard of.
    """

    #: Marks a value this wrapper produced, so a plaintext row written before
    #: encryption was switched on is recognised instead of being fed to the
    #: decrypter and reported as corrupt.
    PREFIX = "praisonai:enc:v1:"

    def __init__(self, store: Any, key: str):
        if not key:
            raise SessionEncryptionError(
                "A key is required. Generate one with "
                "praisonaiagents.session.generate_session_key()."
            )
        Fernet, InvalidToken = _load_fernet()
        self._invalid_token = InvalidToken
        try:
            self._fernet = Fernet(key.encode("ascii") if isinstance(key, str) else key)
        except Exception as exc:
            raise SessionEncryptionError(
                "That key is not a valid Fernet key. Generate one with "
                "praisonaiagents.session.generate_session_key()."
            ) from exc
        self._store = store

    # -- crypto -----------------------------------------------------------

    def _encrypt(self, text: Optional[str]) -> Optional[str]:
        if text is None:
            return None
        token = self._fernet.encrypt(str(text).encode("utf-8")).decode("ascii")
        return f"{self.PREFIX}{token}"

    def _decrypt(self, text: Optional[str]) -> Optional[str]:
        if text is None or not isinstance(text, str):
            return text
        if not text.startswith(self.PREFIX):
            # Written before encryption was enabled. Returned as-is rather than
            # raising, so switching this on does not make old history unreadable.
            return text
        token = text[len(self.PREFIX):]
        try:
            return self._fernet.decrypt(token.encode("ascii")).decode("utf-8")
        except self._invalid_token as exc:
            raise SessionEncryptionError(
                "Could not decrypt a stored message: the key does not match the "
                "one it was written with. Session transcripts are unrecoverable "
                "without their original key."
            ) from exc

    def _encrypt_metadata(self, metadata: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if not metadata:
            return metadata
        return {"__enc__": self._encrypt(json.dumps(metadata, default=str))}

    def _decrypt_metadata(self, metadata: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if not isinstance(metadata, dict) or "__enc__" not in metadata:
            return metadata
        raw = self._decrypt(metadata["__enc__"])
        try:
            return json.loads(raw) if raw else {}
        except (TypeError, ValueError):
            return {}

    # -- wrapped surface --------------------------------------------------

    def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        return self._store.add_message(
            session_id, role, self._encrypt(content), self._encrypt_metadata(metadata)
        )

    def get_chat_history(self, session_id: str, max_messages: Optional[int] = None) -> List[Dict[str, Any]]:
        rows = self._store.get_chat_history(session_id, max_messages)
        out = []
        for row in rows or []:
            if not isinstance(row, dict):
                out.append(row)
                continue
            decoded = dict(row)
            if "content" in decoded:
                decoded["content"] = self._decrypt(decoded["content"])
            if "metadata" in decoded:
                decoded["metadata"] = self._decrypt_metadata(decoded["metadata"])
            out.append(decoded)
        return out

    def search(self, *args: Any, **kwargs: Any):
        raise SessionEncryptionError(
            "Session content is encrypted at rest, so search() cannot match it: "
            "the stored text is ciphertext. Returning no results would be "
            "indistinguishable from a genuine miss, which is why this raises. "
            "Load a session with get_chat_history() and filter in memory, or use "
            "an unencrypted store if search matters more than confidentiality."
        )

    def __getattr__(self, name: str) -> Any:
        """Forward anything not wrapped above to the underlying store."""
        return getattr(self._store, name)
