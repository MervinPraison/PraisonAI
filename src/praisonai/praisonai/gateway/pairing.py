"""
HMAC-signed pairing store for secure channel authorisation.

Generates short human-readable codes that external channels (Slack, Telegram,
UI) present to prove they are authorised to communicate with the gateway.

This is a *heavy implementation* and lives in the wrapper, not the core SDK.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import secrets
import tempfile
import time
import threading
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# Where pairing data is persisted
_DEFAULT_STORE_DIR = os.path.join(
    os.path.expanduser("~"), ".praisonai", "gateway"
)
_DEFAULT_STORE_FILE = "pairing.json"


def _get_secret() -> str:
    """Return the HMAC signing secret.

    Uses ``PRAISONAI_GATEWAY_SECRET`` env-var when set; otherwise generates
    a per-process random secret (codes will NOT survive restarts).
    """
    return os.environ.get("PRAISONAI_GATEWAY_SECRET", "") or secrets.token_hex(32)


@dataclass
class PairedChannel:
    """Record of an authorised external channel."""

    channel_id: str
    channel_type: str  # e.g. "slack", "telegram", "ui"
    paired_at: float = field(default_factory=time.time)
    label: str = ""  # optional human-readable label


class PairingStore:
    """File-backed store of pairing codes and authorised channels.

    The store generates *8-character* hex codes signed with HMAC-SHA256.
    A channel presents the code to the gateway; the gateway verifies
    the signature and adds the channel to the allow-list.

    Thread-safe via ``threading.Lock``.

    Security:
        - Codes are one-time use (consumed on verify).
        - HMAC-signed to prevent forgery.
        - Timing-safe comparison via ``hmac.compare_digest``.
        - Atomic file writes (tempfile + rename) to prevent corruption.
        - Configurable TTL for pending codes.
        - Max pending code limit to prevent memory exhaustion.

    Args:
        store_dir: Directory to persist pairing data (default ``~/.praisonai/gateway``).
        code_ttl:  Seconds before an unused pairing code expires (default 300 = 5 min).
        secret:    HMAC secret; falls back to ``_get_secret()``.
        max_pending: Maximum pending codes at any time (default 100).

    Example::

        store = PairingStore()
        code = store.generate_code(channel_type="slack", channel_id="C12345")
        print(f"Enter this code in Slack: {code}")

        # Later, when the Slack bot sends the code:
        ok = store.verify_and_pair(code, channel_id=None, channel_type="slack")
        assert ok

        # Check if paired
        assert store.is_paired("C12345", "slack")
    """

    def __init__(
        self,
        store_dir: Optional[str] = None,
        code_ttl: float = 300.0,
        secret: Optional[str] = None,
        max_pending: int = 100,
    ) -> None:
        self._dir = store_dir or _DEFAULT_STORE_DIR
        self._path = os.path.join(self._dir, _DEFAULT_STORE_FILE)
        self._code_ttl = code_ttl
        self._secret = (secret or _get_secret()).encode()
        self._max_pending = max_pending
        self._lock = threading.Lock()

        # code -> {signature, channel_type, created_at}
        self._pending: Dict[str, dict] = {}
        # (channel_id, channel_type) -> PairedChannel
        self._paired: Dict[tuple, PairedChannel] = {}

        self._load()

    # ── Code lifecycle ────────────────────────────────────────────────

    def generate_code(self, channel_type: str = "unknown", channel_id: Optional[str] = None) -> str:
        """Generate a new 8-char pairing code.

        The code is HMAC-signed so the gateway can verify it was not forged.
        Raises ``RuntimeError`` if max pending codes is reached.
        """
        code = secrets.token_hex(4)  # 8 hex chars
        sig = self._sign(code)

        with self._lock:
            self._prune_expired()
            if len(self._pending) >= self._max_pending:
                raise RuntimeError(
                    f"Too many pending pairing codes (max={self._max_pending}). "
                    "Wait for existing codes to expire or be consumed."
                )
            self._pending[code] = {
                "signature": sig,
                "channel_type": channel_type,
                "channel_id": channel_id,
                "created_at": time.time(),
            }
        return code

    def verify_and_pair(
        self,
        code: str,
        channel_id: Optional[str],
        channel_type: str,
        label: str = "",
    ) -> bool:
        """Verify a pairing code and, if valid, authorise the channel.

        Returns ``True`` on success, ``False`` on invalid / expired code.
        The code is consumed (one-time use) regardless of outcome.
        If ``channel_id`` is omitted, a channel-bound pending code may provide it.
        """
        with self._lock:
            self._prune_expired()
            pending = self._pending.pop(code, None)

        if pending is None:
            return False

        # Timing-safe comparison
        expected_sig = self._sign(code)
        if not hmac.compare_digest(pending["signature"], expected_sig):
            return False

        pending_channel_id = pending.get("channel_id")
        if pending_channel_id and channel_id and channel_id != pending_channel_id:
            return False

        resolved_channel_id = channel_id or pending_channel_id
        if not resolved_channel_id:
            return False

        paired = PairedChannel(
            channel_id=resolved_channel_id,
            channel_type=channel_type,
            paired_at=time.time(),
            label=label,
        )

        with self._lock:
            self._paired[(resolved_channel_id, channel_type)] = paired
            self._save()

        logger.info("Channel paired: %s (%s)", resolved_channel_id, channel_type)
        return True

    # ── Query API ─────────────────────────────────────────────────────

    def is_paired(self, channel_id: str, channel_type: str) -> bool:
        """Check if a channel is authorised."""
        with self._lock:
            return (channel_id, channel_type) in self._paired

    def list_paired(self) -> List[PairedChannel]:
        """List all authorised channels."""
        with self._lock:
            return list(self._paired.values())

    def list_pending(self) -> List[dict]:
        """List all pending pairing codes."""
        with self._lock:
            self._prune_expired()
            return [
                {"code": code, **info} 
                for code, info in self._pending.items()
            ]

    def revoke(self, channel_id: str, channel_type: str) -> bool:
        """Revoke a paired channel.  Returns ``True`` if it existed."""
        with self._lock:
            removed = self._paired.pop((channel_id, channel_type), None)
            if removed:
                self._save()
                logger.info("Channel revoked: %s (%s)", channel_id, channel_type)
            return removed is not None

    # ── Persistence ───────────────────────────────────────────────────

    def _save(self) -> None:
        """Persist paired channels to disk atomically (caller holds lock).

        Writes to a temp file then renames — prevents corruption on crash.
        """
        try:
            Path(self._dir).mkdir(parents=True, exist_ok=True)
            data = {
                "paired": [
                    asdict(ch) for ch in self._paired.values()
                ],
            }
            # Atomic write: tempfile → rename
            fd, tmp_path = tempfile.mkstemp(
                dir=self._dir, suffix=".tmp", prefix="pairing_"
            )
            try:
                with os.fdopen(fd, "w") as fh:
                    json.dump(data, fh, indent=2)
                os.replace(tmp_path, self._path)  # atomic on POSIX
            except Exception:
                # Clean up temp file on failure
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
                raise
        except OSError as exc:
            logger.warning("Failed to save pairing store: %s", exc)

    def _load(self) -> None:
        """Load paired channels from disk."""
        if not os.path.exists(self._path):
            return
        try:
            with open(self._path) as fh:
                data = json.load(fh)
            for entry in data.get("paired", []):
                ch = PairedChannel(**entry)
                self._paired[(ch.channel_id, ch.channel_type)] = ch
            logger.debug("Loaded %d paired channels", len(self._paired))
        except (OSError, json.JSONDecodeError, TypeError) as exc:
            logger.warning("Failed to load pairing store: %s", exc)

    # ── Internal ──────────────────────────────────────────────────────

    def _sign(self, code: str) -> str:
        return hmac.new(self._secret, code.encode(), hashlib.sha256).hexdigest()

    def _prune_expired(self) -> None:
        """Remove expired pending codes (caller holds lock)."""
        now = time.time()
        expired = [
            c for c, info in self._pending.items()
            if (now - info["created_at"]) >= self._code_ttl
        ]
        for c in expired:
            del self._pending[c]
