"""
WhatsApp Web adapter using neonize (whatsmeow/Go backend).

Provides token-free WhatsApp connectivity via QR code scan and
WhatsApp Linked Devices. Credentials persist locally in SQLite.

This is an OPTIONAL adapter — neonize is lazily imported and only
required when mode="web" is used.

⚠️ EXPERIMENTAL: Uses reverse-engineered WhatsApp Web protocol.
   Your number may be banned by Meta. Use Cloud API for production.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from pathlib import Path
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)

# Default credential storage path
DEFAULT_CREDS_DIR = os.path.join(str(Path.home()), ".praisonai", "whatsapp")


class WhatsAppWebAdapter:
    """Adapter wrapping neonize's async WhatsApp Web client.

    Isolates neonize's API surface behind a stable interface so the
    rest of PraisonAI is shielded from neonize version changes.

    Key design decisions:
    - neonize is imported lazily in connect() only
    - Go FFI callbacks are bridged to asyncio via loop.call_soon_threadsafe()
    - Credentials stored in SQLite (neonize default) at creds_dir
    """

    def __init__(
        self,
        creds_dir: Optional[str] = None,
        bot_name: str = "praisonai_whatsapp",
        on_message: Optional[Callable] = None,
        on_qr: Optional[Callable] = None,
        on_connected: Optional[Callable] = None,
        on_disconnected: Optional[Callable] = None,
    ):
        self._creds_dir = creds_dir or os.environ.get(
            "WHATSAPP_CREDS_DIR", DEFAULT_CREDS_DIR
        )
        self._bot_name = bot_name
        self._on_message = on_message
        self._on_qr = on_qr
        self._on_connected = on_connected
        self._on_disconnected = on_disconnected

        self._client: Any = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._is_connected = False
        self._self_jid: Optional[str] = None
        self._started_at: Optional[float] = None

    @property
    def is_connected(self) -> bool:
        return self._is_connected

    @property
    def connected_at(self) -> Optional[float]:
        """Epoch seconds when the adapter received ConnectedEv."""
        return self._started_at

    @property
    def self_jid(self) -> Optional[str]:
        return self._self_jid

    @property
    def creds_dir(self) -> str:
        return self._creds_dir

    def _ensure_creds_dir(self) -> None:
        """Create credentials directory if it doesn't exist."""
        os.makedirs(self._creds_dir, exist_ok=True)

    def _get_db_path(self) -> str:
        """Get SQLite database path for neonize credentials."""
        self._ensure_creds_dir()
        return os.path.join(self._creds_dir, f"{self._bot_name}.db")

    async def connect(self) -> None:
        """Connect to WhatsApp via neonize.

        Displays QR code if no saved session exists.
        Uses saved credentials if available.
        """
        try:
            from neonize.aioze.client import NewAClient
            from neonize.aioze.events import ConnectedEv, MessageEv
        except ImportError:
            raise ImportError(
                "neonize is required for WhatsApp Web mode. "
                "Install with: pip install 'praisonai[bot-whatsapp-web]' "
                "or: pip install neonize"
            )

        self._loop = asyncio.get_running_loop()
        db_path = self._get_db_path()

        logger.info(f"WhatsApp Web: connecting (creds: {db_path})")

        # ── Suppress noisy Go-backend warnings ─────────────────────
        # whatsmeow emits non-actionable warnings (websocket EOF on
        # close, LTHash mismatches during state sync, duplicate
        # contacts, missing MAC values, decryption failures for old
        # keys). These are protocol-level quirks, not bugs in our
        # code — suppress to reduce noise.
        _known_noise = (
            "failed to close WebSocket",
            "Error sending close to websocket",
            "duplicate contacts found",
            "mismatching LTHash",
            "missing value MAC",
            "failed to decrypt prekey message",
            "failed to decrypt group message",
            "received message with old counter",
            "failed to read frame header",
        )

        class _WhatsmeowNoiseFilter(logging.Filter):
            def filter(self, record: logging.LogRecord) -> bool:
                msg = record.getMessage()
                return not any(pat in msg for pat in _known_noise)

        # Apply to the root "whatsmeow" logger so ALL child loggers
        # (whatsmeow.Client, whatsmeow.Database, etc.) inherit it.
        # Also apply to neonize's own log module logger.
        _noise_filter = _WhatsmeowNoiseFilter()
        for _logger_name in ("whatsmeow", "neonize.utils.log"):
            _wm_logger = logging.getLogger(_logger_name)
            _wm_logger.addFilter(_noise_filter)

        # ── Critical: bridge neonize's event loop to ours ──────────
        # neonize creates event_global_loop = asyncio.new_event_loop()
        # at import time but NEVER starts it. Go-thread callbacks
        # (QR, messages, connected) are posted to that dead loop via
        # asyncio.run_coroutine_threadsafe(..., event_global_loop).
        # Fix: replace it with the currently running loop so callbacks
        # actually execute.
        import neonize.aioze.events as _nz_events
        import neonize.aioze.client as _nz_client
        _nz_events.event_global_loop = self._loop
        _nz_client.event_global_loop = self._loop

        # neonize uses `name` as the DB file path directly
        self._client = NewAClient(db_path)
        # Also patch the client instance's loop reference
        self._client.loop = self._loop

        # Register event handlers via neonize's Event system
        # client.event is an Event instance; calling it with an event type
        # returns a decorator that registers the handler.
        @self._client.event(ConnectedEv)
        async def on_connected(client: Any, event: ConnectedEv) -> None:
            self._is_connected = True
            self._started_at = time.time()
            # Extract self JID from client.me (set by neonize on Device event)
            try:
                if client.me is not None:
                    self._self_jid = str(client.me)
            except Exception:
                self._self_jid = None
            logger.info("WhatsApp Web: connected")
            if self._on_connected:
                await self._safe_callback(self._on_connected)

        @self._client.event(MessageEv)
        async def on_message(client: Any, event: MessageEv) -> None:
            if self._on_message:
                await self._safe_callback(self._on_message, event)

        # QR handler uses the dedicated event.qr() registration
        @self._client.event.qr
        async def on_qr(client: Any, qr_bytes: bytes) -> None:
            qr_data = qr_bytes.decode() if isinstance(qr_bytes, bytes) else str(qr_bytes)
            logger.info("WhatsApp Web: QR code received — scan with your phone")
            if self._on_qr:
                await self._safe_callback(self._on_qr, qr_data)
            else:
                # Default: print QR to terminal
                self._print_qr_terminal(qr_data)

        try:
            await self._client.connect()
        except Exception as e:
            self._is_connected = False
            logger.error(f"WhatsApp Web connection failed: {e}")
            raise

    async def disconnect(self) -> None:
        """Disconnect from WhatsApp."""
        self._is_connected = False
        if self._client:
            try:
                await self._client.disconnect()
            except Exception as e:
                logger.warning(f"WhatsApp Web disconnect error: {e}")
            self._client = None
        logger.info("WhatsApp Web: disconnected")
        if self._on_disconnected:
            await self._safe_callback(self._on_disconnected)

    async def send_message(self, to: Any, text: str) -> Optional[str]:
        """Send a text message via WhatsApp Web.

        Args:
            to: Recipient — a native neonize JID protobuf object (preferred,
                preserves LID routing info) OR a JID string / phone number
                (e.g., "1234567890@s.whatsapp.net") as fallback.
            text: Message text

        Returns:
            Message ID if sent successfully, None otherwise.
        """
        if not self._client or not self._is_connected:
            logger.error("WhatsApp Web: not connected, cannot send message")
            return None

        try:
            # If *to* is already a neonize JID protobuf, use it directly.
            # This preserves LID routing info and avoids "no LID found" errors.
            target_jid = to
            if isinstance(to, str):
                jid_str = self._normalize_jid(to)
                from neonize.utils import build_jid
                parts = jid_str.split("@", 1)
                user = parts[0]
                server = parts[1] if len(parts) > 1 else "s.whatsapp.net"
                target_jid = build_jid(user, server)

            resp = await self._client.send_message(target_jid, text)
            msg_id = getattr(resp, 'ID', None) or str(resp)
            return str(msg_id)
        except Exception as e:
            logger.error(f"WhatsApp Web send error: {e}")
            return None

    async def send_reaction(self, to: str, message_id: str, emoji: str) -> None:
        """Send a reaction to a message."""
        if not self._client or not self._is_connected:
            return
        try:
            jid = self._normalize_jid(to)
            await self._client.send_reaction(jid, message_id, emoji)
        except Exception as e:
            logger.error(f"WhatsApp Web reaction error: {e}")

    async def mark_as_read(self, to: str, message_id: str) -> None:
        """Mark a message as read."""
        if not self._client or not self._is_connected:
            return
        try:
            jid = self._normalize_jid(to)
            await self._client.mark_read(jid, message_id)
        except Exception as e:
            logger.error(f"WhatsApp Web mark_read error: {e}")

    def has_saved_session(self) -> bool:
        """Check if saved credentials exist."""
        db_path = self._get_db_path()
        return os.path.exists(db_path) and os.path.getsize(db_path) > 0

    async def logout(self) -> None:
        """Logout and clear saved credentials."""
        await self.disconnect()
        db_path = self._get_db_path()
        if os.path.exists(db_path):
            os.remove(db_path)
            logger.info(f"WhatsApp Web: cleared credentials at {db_path}")
        # Also remove WAL/SHM files
        for suffix in (".db-wal", ".db-shm"):
            p = db_path.replace(".db", suffix)
            if os.path.exists(p):
                os.remove(p)

    # ── Internal helpers ─────────────────────────────────────────

    @staticmethod
    def _normalize_jid(phone_or_jid: str) -> str:
        """Normalize a phone number to WhatsApp JID format."""
        jid = phone_or_jid.strip()
        if "@" in jid:
            return jid
        # Remove + prefix and non-digits
        digits = "".join(c for c in jid if c.isdigit())
        return f"{digits}@s.whatsapp.net"

    @staticmethod
    def _print_qr_terminal(qr_data: str) -> None:
        """Print QR code to terminal. Uses segno (neonize dep) or qrcode."""
        try:
            import segno  # type: ignore  — installed with neonize
            print("\n" + "=" * 50)
            print("Scan this QR code in WhatsApp → Linked Devices:")
            print("=" * 50)
            segno.make_qr(qr_data).terminal(compact=True)
            print("=" * 50 + "\n")
            return
        except Exception:
            pass
        try:
            import qrcode  # type: ignore
            qr = qrcode.QRCode(border=1)
            qr.add_data(qr_data)
            qr.print_ascii(tty=True)
            return
        except ImportError:
            pass
        # Final fallback: raw data
        print(f"\n{'='*50}")
        print("Scan this QR code in WhatsApp → Linked Devices:")
        print(f"QR Data: {qr_data[:80]}...")
        print(f"{'='*50}")
        print("(Install 'segno' or 'qrcode' for visual QR display)")

    async def _safe_callback(self, callback: Callable, *args: Any) -> None:
        """Safely invoke a callback, handling both sync and async."""
        try:
            result = callback(*args)
            if asyncio.iscoroutine(result):
                await result
        except Exception as e:
            logger.error(f"WhatsApp Web callback error: {e}")
