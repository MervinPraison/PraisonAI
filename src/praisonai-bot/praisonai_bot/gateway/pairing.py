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

# Unambiguous alphabet for human-entered codes (drops 0/O/1/I) so a code
# read aloud or retyped from another device is not mis-entered.
_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
_CODE_LENGTH = 8

# Store-level brute-force ceiling defaults (per channel_type). These guard the
# verification path uniformly across every approval surface (HTTP, in-chat
# button, CLI) — the optional IP-keyed HTTP limiter remains an outer layer.
_LOCKOUT_MAX_FAILURES = 5
_LOCKOUT_WINDOW_SECONDS = 60.0
_LOCKOUT_COOLDOWN_SECONDS = 300.0


def _get_secret() -> str:
    """Return the HMAC signing secret.

    An explicit ``PRAISONAI_GATEWAY_SECRET`` override wins; otherwise the
    persisted, auto-provisioned secret is loaded (and created 0600 on first
    use) so pairing codes survive process restarts with zero operator action.
    """
    return _load_or_create_secret(_DEFAULT_STORE_DIR).decode()


def _secure_secret_permissions(secret_path: str) -> None:
    """Ensure <secret_path> is owner-only (0600), remediating insecure modes.

    On POSIX the file is ``chmod`` ed to ``0o600`` when its mode differs.
    On Windows ``os.chmod`` cannot express owner-only ACLs, so we attempt a
    best-effort restriction via ``icacls`` and downgrade the message to debug
    when it is unavailable (avoids per-init warning spam).

    Raises ``OSError`` if a POSIX ``chmod`` fails, allowing the caller to
    decide whether to fail closed.
    """
    import stat

    mode = stat.S_IMODE(os.stat(secret_path).st_mode)
    if mode == 0o600:
        return

    if os.name == "nt":
        # POSIX mode bits are unreliable on Windows; attempt an ACL lockdown.
        if _restrict_windows_acl(secret_path):
            logger.debug(
                "Restricted gateway secret ACL to current user: %s", secret_path
            )
        else:
            logger.debug(
                "Gateway secret file %s reports mode %s on Windows; "
                "POSIX permissions are not authoritative here.",
                secret_path,
                oct(mode),
            )
        return

    # POSIX: remediate by chmod-ing to owner-only.
    try:
        os.chmod(secret_path, 0o600)
        logger.info(
            "Remediated insecure gateway secret permissions %s -> 0o600 at %s",
            oct(mode),
            secret_path,
        )
    except OSError as exc:
        logger.error(
            "Failed to secure gateway secret %s (mode %s): %s",
            secret_path,
            oct(mode),
            exc,
        )
        raise


def _restrict_windows_acl(secret_path: str) -> bool:
    """Best-effort restrict a file's ACL to the current user on Windows.

    Returns ``True`` when the ACL was applied, ``False`` otherwise. Never
    raises — callers treat failure as non-fatal.
    """
    try:
        import getpass

        from .._guarded_subprocess import run_guarded

        user = os.environ.get("USERNAME") or getpass.getuser()
        # Resolve icacls from the trusted system directory rather than PATH
        # to avoid invoking a hijacked binary while hardening the secret.
        icacls = os.path.join(
            os.environ.get("SystemRoot", r"C:\Windows"),
            "System32",
            "icacls.exe",
        )
        # Quote the username so principals containing spaces (e.g. "John Doe")
        # are parsed as a single principal by icacls.
        # Bounded: this runs while hardening the pairing secret on the gateway
        # startup path, so a stalled icacls must not block it forever.
        result = run_guarded(
            [
                icacls,
                secret_path,
                "/inheritance:r",
                "/grant:r",
                f'"{user}":F',
            ],
            timeout=15,
            check=False,
        )
        return result.returncode == 0
    except Exception:  # pragma: no cover - defensive, Windows-only path
        return False


def _load_or_create_secret(store_dir: str) -> bytes:
    """Persist per-install secret at <store_dir>/.gateway_secret (0600).

    This ensures HMAC signatures remain consistent across process restarts,
    allowing pairing codes to work between gateway and CLI processes.

    Existing files with insecure permissions are remediated to ``0o600``
    (POSIX) or restricted via ACL (Windows) instead of merely warning.
    """
    env = os.environ.get("PRAISONAI_GATEWAY_SECRET")
    if env:
        return env.encode()

    os.makedirs(store_dir, exist_ok=True)
    secret_path = os.path.join(store_dir, ".gateway_secret")

    if os.path.exists(secret_path):
        try:
            with open(secret_path, "rb") as f:
                secret = f.read().strip()
        except (OSError, IOError) as e:
            # Do not silently regenerate on a read failure of an *existing*
            # secret — that would rotate the HMAC key and invalidate every
            # outstanding pairing code. Fail closed so the caller sees it.
            logger.error(f"Failed to read gateway secret from {secret_path}: {e}")
            raise
        # Reject an empty/whitespace-only file: an empty HMAC key would let
        # pairing/callback signatures be forged. Regenerate below instead.
        if secret:
            # Remediate insecure permissions instead of warn-and-load.
            # A chmod failure here propagates (fail closed) rather than
            # being swallowed and silently regenerating the secret.
            _secure_secret_permissions(secret_path)
            return secret
        logger.warning(
            "Gateway secret at %s is empty; regenerating.", secret_path
        )

    # Generate new secret. Use exclusive creation (O_EXCL) so two racing
    # processes cannot each write a different secret and then diverge — the
    # loser re-reads the winner's persisted secret instead.
    secret = secrets.token_hex(32).encode()
    try:
        fd = os.open(secret_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        # Another process created it first; adopt its secret.
        try:
            with open(secret_path, "rb") as f:
                existing = f.read().strip()
            if existing:
                _secure_secret_permissions(secret_path)
                return existing
        except (OSError, IOError) as e:
            logger.warning(
                f"Failed to read gateway secret written by peer at "
                f"{secret_path}: {e}"
            )
        return secret
    except (OSError, IOError) as e:
        logger.warning(f"Failed to save gateway secret to {secret_path}: {e}")
        # Fall back to in-memory secret for this process
        return secret

    try:
        with os.fdopen(fd, "wb") as f:
            f.write(secret)
        # On Windows the 0o600 open flag is not authoritative; lock down ACL.
        _secure_secret_permissions(secret_path)
        logger.info(f"Generated new gateway secret at {secret_path}")
    except (OSError, IOError) as e:
        logger.warning(f"Failed to save gateway secret to {secret_path}: {e}")
        # Fall back to in-memory secret for this process

    return secret


@dataclass
class PairedChannel:
    """Record of an authorised external channel."""

    channel_id: str
    channel_type: str  # e.g. "slack", "telegram", "ui"
    paired_at: float = field(default_factory=time.time)
    label: str = ""  # optional human-readable label


class PairingStore:
    """File-backed store of pairing codes and authorised channels.

    The store generates *8-character* codes (from an unambiguous alphabet that
    drops ``0/O/1/I``) signed with HMAC-SHA256. A channel presents the code to
    the gateway; the gateway verifies the signature and adds the channel to the
    allow-list.

    Thread-safe via ``threading.Lock``.

    Security:
        - Codes are one-time use (consumed on verify).
        - HMAC-signed to prevent forgery.
        - Only a salted hash of each code is persisted — reading the state
          file never yields a usable pairing code.
        - Store-level brute-force ceiling: failed verifications are counted
          per channel_type and locked out after ``max_failures``, uniformly
          across every approval surface (HTTP, in-chat button, CLI).
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
        max_failures: int = _LOCKOUT_MAX_FAILURES,
        lockout_window: float = _LOCKOUT_WINDOW_SECONDS,
        lockout_cooldown: float = _LOCKOUT_COOLDOWN_SECONDS,
    ) -> None:
        self._dir = store_dir or _DEFAULT_STORE_DIR
        self._path = os.path.join(self._dir, _DEFAULT_STORE_FILE)
        self._code_ttl = code_ttl
        self._secret = secret.encode() if secret else _load_or_create_secret(self._dir)
        self._max_pending = max_pending
        self._lock = threading.Lock()

        # code -> {signature, channel_type, created_at}  (raw code in memory only)
        self._pending: Dict[str, dict] = {}
        # code_hash -> {signature, channel_type, created_at}  (rehydrated from disk;
        # lets verification succeed cross-process without persisting the raw code)
        self._pending_by_hash: Dict[str, dict] = {}
        # (channel_id, channel_type) -> PairedChannel
        self._paired: Dict[tuple, PairedChannel] = {}

        # Store-level brute-force ceiling, keyed by channel_type. Reuses the
        # gateway's own limiter so protection is uniform across every approval
        # surface (HTTP, in-chat button, CLI), not just the HTTP routes.
        from .rate_limiter import AuthRateLimiter

        self._lockout = AuthRateLimiter(
            max_attempts=max_failures,
            window_seconds=lockout_window,
            lockout_seconds=lockout_cooldown,
        )

        self._load()

    # ── Code lifecycle ────────────────────────────────────────────────

    def generate_code(self, channel_type: str = "unknown", channel_id: Optional[str] = None) -> str:
        """Generate a new 8-char pairing code.

        The code is HMAC-signed so the gateway can verify it was not forged.
        Raises ``RuntimeError`` if max pending codes is reached.
        """
        code = "".join(secrets.choice(_CODE_ALPHABET) for _ in range(_CODE_LENGTH))
        sig = self._sign(code)

        with self._lock:
            self._prune_expired()
            # Count *all* logical pending entries, including ones rehydrated
            # from disk into ``_pending_by_hash`` after a restart. ``_pending``
            # alone under-counts cross-process state, letting repeated restarts
            # grow ``pairing.json`` past ``max_pending``.
            if len(self._pending_by_hash) >= self._max_pending:
                raise RuntimeError(
                    f"Too many pending pairing codes (max={self._max_pending}). "
                    "Wait for existing codes to expire or be consumed."
                )
            info = {
                "signature": sig,
                "channel_type": channel_type,
                "channel_id": channel_id,
                "created_at": time.time(),
            }
            self._pending[code] = info
            self._pending_by_hash[self._hash(code)] = dict(info)
            self._save()  # NEW — persist pending codes (hashed at rest)
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
        # Store-level brute-force ceiling: refuse verification for a channel
        # type that has exceeded its failed-attempt budget, regardless of which
        # approval surface (HTTP, in-chat, CLI) is calling. Checking the lockout
        # here does not itself count as an attempt — only failures are counted.
        if self._locked_out(channel_type):
            logger.warning(
                "Pairing verification locked out for channel_type=%s", channel_type
            )
            return False

        with self._lock:
            self._prune_expired()
            pending = self._pending.pop(code, None)
            if pending is None:
                # Cross-process fallback: the raw code was never persisted, so
                # match against the salted hash rehydrated from disk.
                pending = self._pending_by_hash.pop(self._hash(code), None)
            if pending is not None:
                self._pending_by_hash.pop(self._hash(code), None)
                self._save()  # NEW — persist the pop

        if pending is None:
            self._record_failure(channel_type)
            return False

        # Timing-safe comparison
        expected_sig = self._sign(code)
        if not hmac.compare_digest(pending["signature"], expected_sig):
            self._record_failure(channel_type)
            return False

        # Validate the channel binding *before* clearing the failure counter.
        # A valid HMAC presented against the wrong ``channel_id`` still fails
        # to pair — clearing the lockout here would hand subsequent guesses a
        # fresh attempt budget after an unsuccessful pairing.
        pending_channel_id = pending.get("channel_id")
        if pending_channel_id and channel_id and channel_id != pending_channel_id:
            return False

        resolved_channel_id = channel_id or pending_channel_id
        if not resolved_channel_id:
            return False

        # Binding is valid — this was a legitimate, successful verification, so
        # the brute-force counter for this channel_type is cleared.
        self._clear_failures(channel_type)

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

    def revoke(self, channel_id: str, channel_type: str) -> bool:
        """Revoke a paired channel.  Returns ``True`` if it existed."""
        with self._lock:
            removed = self._paired.pop((channel_id, channel_type), None)
            if removed:
                self._save()
                logger.info("Channel revoked: %s (%s)", channel_id, channel_type)
            return removed is not None

    def approve(self, channel_type: str, code: str, user_id: str = "", user_name: str = "") -> bool:
        """Convenience method for approving a pairing code.
        
        Args:
            channel_type: Channel type (e.g., "telegram", "slack")
            code: Pairing code to verify
            user_id: User ID for the channel (optional, uses code if not provided)
            user_name: Human-readable username (optional)
            
        Returns:
            True if approval successful, False if code invalid/expired
            
        Note:
            Current implementation uses pairing code as temporary channel_id when
            no user_id is provided. This is a simplified approval flow where admin
            approval immediately pairs the code. In a full implementation, approval
            would mark the code as "approved" and actual pairing would happen when
            the real user presents the code with their user_id.
        """
        # Use code as channel_id if user_id not provided (current simple implementation)
        channel_id = user_id or code
        label = user_name or f"User {channel_id}"
        return self.verify_and_pair(code, channel_id, channel_type, label)

    def list_pending(self, channel_type: Optional[str] = None) -> List[Dict[str, any]]:
        """List pending pairing requests.
        
        Args:
            channel_type: Optional filter by channel type
            
        Returns:
            List of pending requests with channel, code, user info, and age
        """
        with self._lock:
            self._prune_expired()
            
            pending_list = []
            now = time.time()
            
            in_memory_hashes = set()
            for code, info in self._pending.items():
                in_memory_hashes.add(self._hash(code))
                if channel_type and info.get("channel_type") != channel_type:
                    continue

                ct = info.get("channel_type", "unknown")
                cid = info.get("channel_id")
                created_at = info.get("created_at", now)
                pending_list.append({
                    "code": code,
                    "channel_type": ct,
                    "channel_id": cid,
                    "created_at": created_at,
                    # UI-friendly aliases (used by praisonai.ui._pairing banner)
                    "channel": ct,
                    "user_id": code,
                    "user_name": f"User {code}",
                    "age_seconds": int(now - created_at),
                })

            # Cross-process pending codes rehydrated from disk carry only a
            # salted hash — the raw code was never persisted. Surface them so
            # operators still see a pending request exists (and can approve by
            # re-entering the code from chat), but never expose a usable code.
            for chash, info in self._pending_by_hash.items():
                if chash in in_memory_hashes:
                    continue
                if channel_type and info.get("channel_type") != channel_type:
                    continue
                ct = info.get("channel_type", "unknown")
                cid = info.get("channel_id")
                created_at = info.get("created_at", now)
                pending_list.append({
                    "code": None,
                    "code_hash": chash,
                    "channel_type": ct,
                    "channel_id": cid,
                    "created_at": created_at,
                    "channel": ct,
                    "user_id": cid,
                    "user_name": f"User {cid}" if cid else "pending",
                    "age_seconds": int(now - created_at),
                })

        return pending_list

    # ── Persistence ───────────────────────────────────────────────────

    def _save(self) -> None:
        """Persist paired channels to disk atomically (caller holds lock).

        Writes to a temp file then renames — prevents corruption on crash.
        """
        try:
            Path(self._dir).mkdir(parents=True, exist_ok=True)
            # Merge in-memory (raw-code) pending with any cross-process entries
            # rehydrated from disk. Only a salted hash of the code is persisted —
            # reading pairing.json never yields a usable code.
            pending_out = []
            seen_hashes = set()
            for c, info in self._pending.items():
                chash = self._hash(c)
                seen_hashes.add(chash)
                pending_out.append({"code_hash": chash, **info})
            for chash, info in self._pending_by_hash.items():
                if chash in seen_hashes:
                    continue
                pending_out.append({"code_hash": chash, **info})

            data = {
                "paired": [
                    asdict(ch) for ch in self._paired.values()
                ],
                "pending": pending_out,
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
            # Load pending codes. New format persists only a salted ``code_hash``;
            # the legacy plaintext ``code`` field is still read for backward
            # compatibility so existing on-disk stores keep working.
            for entry in data.get("pending", []):
                if "code" in entry:  # legacy plaintext store
                    code = entry.pop("code")
                    self._pending[code] = entry
                    self._pending_by_hash[self._hash(code)] = dict(entry)
                elif "code_hash" in entry:  # hashed-at-rest store
                    chash = entry.pop("code_hash")
                    self._pending_by_hash[chash] = entry
            logger.debug(
                "Loaded %d paired channels, %d pending codes",
                len(self._paired),
                len(self._pending_by_hash),
            )
        except (OSError, json.JSONDecodeError, TypeError) as exc:
            logger.warning("Failed to load pairing store: %s", exc)

    # ── Internal ──────────────────────────────────────────────────────

    def _sign(self, code: str) -> str:
        return hmac.new(self._secret, code.encode(), hashlib.sha256).hexdigest()

    def _hash(self, code: str) -> str:
        """Salted SHA-256 of a code for at-rest storage.

        The salt is derived from the per-install HMAC secret, so the hash is
        stable across processes (enabling cross-process verification) yet a
        precomputed rainbow table is useless without the secret.
        """
        return hashlib.sha256(self._secret + b":" + code.encode()).hexdigest()

    # ── Brute-force ceiling helpers ───────────────────────────────────

    def _locked_out(self, channel_type: str) -> bool:
        return self._lockout.time_until_allowed("pairing_verify", channel_type) > 0

    def _record_failure(self, channel_type: str) -> None:
        # ``allow`` counts this attempt and trips the lockout at the ceiling.
        self._lockout.allow("pairing_verify", channel_type)

    def _clear_failures(self, channel_type: str) -> None:
        self._lockout.reset("pairing_verify", channel_type)

    def _prune_expired(self) -> None:
        """Remove expired pending codes (caller holds lock)."""
        now = time.time()
        expired = [
            c for c, info in self._pending.items()
            if (now - info["created_at"]) >= self._code_ttl
        ]
        for c in expired:
            self._pending_by_hash.pop(self._hash(c), None)
            del self._pending[c]
        expired_hashes = [
            h for h, info in self._pending_by_hash.items()
            if (now - info["created_at"]) >= self._code_ttl
        ]
        for h in expired_hashes:
            del self._pending_by_hash[h]
