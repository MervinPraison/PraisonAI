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
        if not isinstance(metadata, dict):
            return metadata
        # Recognise only the exact one-key envelope this wrapper produces, whose
        # value carries the crypto PREFIX. Legacy metadata that merely happens to
        # contain an "__enc__" key (alongside others, or without the marker) is
        # left untouched rather than being misread and dropped.
        value = metadata.get("__enc__")
        if (
            len(metadata) != 1
            or not isinstance(value, str)
            or not value.startswith(self.PREFIX)
        ):
            return metadata
        raw = self._decrypt(value)
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
        tool_calls: Optional[List[Dict[str, Any]]] = None,
        tool_call_id: Optional[str] = None,
    ) -> bool:
        # tool_calls carry function arguments — as sensitive as content — so they
        # are encrypted too. tool_call_id is an opaque correlation id the store
        # may need to link turns, so it is left readable like the role and ids.
        # These kwargs are only forwarded when present, so wrapping a leaner
        # store whose add_message lacks them keeps working.
        extra: Dict[str, Any] = {}
        if tool_calls is not None:
            extra["tool_calls"] = self._encrypt_tool_calls(tool_calls)
        if tool_call_id is not None:
            extra["tool_call_id"] = tool_call_id
        return self._store.add_message(
            session_id,
            role,
            self._encrypt(content),
            self._encrypt_metadata(metadata),
            **extra,
        )

    def add_user_message(self, session_id: str, content: str, metadata: Optional[Dict[str, Any]] = None) -> bool:
        # The runtime persists ordinary turns through these helpers. Left to the
        # inner store they would call the inner add_message and write plaintext,
        # so the wrapper must own them rather than forward them.
        return self.add_message(session_id, "user", content, metadata)

    def add_assistant_message(self, session_id: str, content: str, metadata: Optional[Dict[str, Any]] = None) -> bool:
        return self.add_message(session_id, "assistant", content, metadata)

    def get_chat_history(self, session_id: str, max_messages: Optional[int] = None) -> List[Dict[str, Any]]:
        rows = self._store.get_chat_history(session_id, max_messages)
        return [self._decrypt_row(row) for row in rows or []]

    def get_working_history(self, session_id: str, *args: Any, **kwargs: Any):
        rows = self._store.get_working_history(session_id, *args, **kwargs)
        return [self._decrypt_row(row) for row in rows or []]

    def get_session(self, session_id: str) -> Any:
        # Session objects expose their turns as a list of message dicts/objects;
        # decrypt those in place so callers see plaintext without the wrapper
        # having to know the concrete session type.
        session = self._store.get_session(session_id)
        messages = getattr(session, "messages", None)
        if isinstance(messages, list):
            for msg in messages:
                self._decrypt_message_obj(msg)
        return session

    # -- helpers ----------------------------------------------------------

    def _encrypt_tool_calls(self, tool_calls):
        if not tool_calls:
            return tool_calls
        return self._encrypt(json.dumps(tool_calls, default=str))

    def _decrypt_tool_calls(self, tool_calls):
        if not isinstance(tool_calls, str) or not tool_calls.startswith(self.PREFIX):
            return tool_calls
        raw = self._decrypt(tool_calls)
        try:
            return json.loads(raw) if raw else tool_calls
        except (TypeError, ValueError):
            return tool_calls

    def _decrypt_row(self, row: Any) -> Any:
        if not isinstance(row, dict):
            return row
        decoded = dict(row)
        if "content" in decoded:
            decoded["content"] = self._decrypt(decoded["content"])
        if "metadata" in decoded:
            decoded["metadata"] = self._decrypt_metadata(decoded["metadata"])
        if decoded.get("tool_calls") is not None:
            decoded["tool_calls"] = self._decrypt_tool_calls(decoded["tool_calls"])
        return decoded

    def _decrypt_message_obj(self, msg: Any) -> None:
        if isinstance(msg, dict):
            if "content" in msg:
                msg["content"] = self._decrypt(msg["content"])
            if "metadata" in msg:
                msg["metadata"] = self._decrypt_metadata(msg["metadata"])
            if msg.get("tool_calls") is not None:
                msg["tool_calls"] = self._decrypt_tool_calls(msg["tool_calls"])
            return
        if hasattr(msg, "content"):
            msg.content = self._decrypt(msg.content)
        if hasattr(msg, "metadata"):
            msg.metadata = self._decrypt_metadata(msg.metadata)
        if getattr(msg, "tool_calls", None) is not None:
            msg.tool_calls = self._decrypt_tool_calls(msg.tool_calls)

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
