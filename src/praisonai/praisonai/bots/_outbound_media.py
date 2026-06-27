"""
Outbound media delivery + delivery-path safety guard (Issue #2388).

The agent-callable ``send_message`` tool already accepts a ``media`` list, but
the gateway's outbound binding historically *dropped* every attachment: the
model could describe a generated chart/PDF/CSV in text but never actually
deliver the file to the user's chat. This module supplies the two missing
pieces, both wrapper-only by design:

1. :func:`validate_media_delivery_path` — an exfiltration guard run *before*
   any upload. Because the file path is model-controlled, prompt injection
   could try to name a local secret (``~/.ssh``, ``~/.aws``, ``/etc``, the
   gateway's own pairing/secret state) as the "file to send". The guard
   resolves symlinks, rejects a credential/system denylist, and supports an
   optional strict mode (allowlist roots **or** a recently-produced mtime
   window) for multi-tenant/hosted gateways.

2. :func:`deliver_media_to_adapter` — routes a validated path through whatever
   upload primitive the live platform adapter exposes
   (Telegram ``send_photo``/``send_document``, Slack ``files_upload_v2``,
   Discord channel file send), degrading gracefully when an adapter cannot
   attach files.

Core stays protocol-only: the actual SDK upload calls (heavy, optional deps)
live here in the wrapper alongside the adapters they drive.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, List, Optional

logger = logging.getLogger(__name__)


# Credential / system locations an agent must never be tricked into sending.
# Matched against the *resolved* (symlink-free) absolute path so a symlink or
# ``..`` traversal cannot smuggle a denied location past the check. Each entry
# is treated as a directory prefix: a path is denied when it equals the entry
# or sits anywhere beneath it.
_DENY_PREFIXES: List[str] = [
    "/etc",
    "/proc",
    "/sys",
    "/dev",
    "/root",
    "/boot",
    "/var/run",
    "/run",
]

# Sensitive dot-directories/files resolved relative to the user's home. These
# are the classic exfiltration targets (SSH keys, cloud creds, shell history,
# gateway pairing/secret state) named by basename-anywhere-in-path.
_DENY_HOME_SUBDIRS: List[str] = [
    ".ssh",
    ".aws",
    ".gnupg",
    ".config/gcloud",
    ".kube",
    ".docker",
    ".netrc",
    ".git-credentials",
    ".praisonai/state",
    ".praisonai/secrets",
    ".praisonai/pairing",
]


class MediaDeliveryError(Exception):
    """Raised when an outbound media path fails the delivery-path guard."""


@dataclass
class OutboundMediaPolicy:
    """Policy controlling which agent-supplied paths may be uploaded.

    Attributes:
        enabled: Master switch. When ``False``, no media is ever uploaded
            (the historical behaviour) and text is still delivered.
        strict: When ``True``, a path must additionally satisfy *either*
            ``allow_roots`` membership *or* the recent-mtime window. Intended
            for multi-tenant / hosted gateways where only freshly produced
            files should be sendable.
        allow_roots: Allowlisted directory roots for strict mode. A path is
            accepted when it resolves to within one of these roots.
        max_bytes: Hard per-file size cap. ``0``/negative disables the cap.
        recent_mtime_seconds: In strict mode, a file modified within this many
            seconds is treated as "recently produced" and allowed even when it
            is outside ``allow_roots``. ``0`` disables the mtime window.
    """

    enabled: bool = True
    strict: bool = False
    allow_roots: List[str] = field(default_factory=list)
    max_bytes: int = 20 * 1024 * 1024
    recent_mtime_seconds: int = 3600

    @classmethod
    def from_dict(cls, data: Optional[dict]) -> "OutboundMediaPolicy":
        """Build a policy from a ``media_delivery`` YAML/dict block.

        Unknown keys are ignored so the schema can evolve without breaking
        older configs; absent keys fall back to the safe defaults above.
        """
        if not isinstance(data, dict):
            return cls()
        roots = data.get("allow_roots") or []
        if isinstance(roots, str):
            roots = [roots]
        try:
            roots = [str(r) for r in roots]
        except TypeError:
            roots = []
        return cls(
            enabled=bool(data.get("enabled", True)),
            strict=bool(data.get("strict", False)),
            allow_roots=roots,
            max_bytes=int(data.get("max_bytes", 20 * 1024 * 1024)),
            recent_mtime_seconds=int(data.get("recent_mtime_seconds", 3600)),
        )


def _resolved(path: str) -> Path:
    """Resolve a path to an absolute, symlink-free :class:`Path`.

    ``strict=False`` so a non-existent path still resolves (we surface a
    clearer "not found" error afterwards) while existing symlinks are
    canonicalised before the denylist check runs.
    """
    return Path(path).expanduser().resolve(strict=False)


def _is_within(child: Path, parent: Path) -> bool:
    """Return True if ``child`` equals or is nested under ``parent``."""
    try:
        child.relative_to(parent)
        return True
    except ValueError:
        return False


def validate_media_delivery_path(
    path: str,
    *,
    policy: Optional[OutboundMediaPolicy] = None,
) -> str:
    """Validate an agent-supplied outbound media path before upload.

    The path is model-controlled, so this guard is the exfiltration boundary:
    it resolves symlinks, rejects a credential/system denylist, enforces a size
    cap, and (in strict mode) requires the file to live under an allowlisted
    root or to have been produced recently.

    Args:
        path: The local filesystem path the agent asked to deliver.
        policy: The active :class:`OutboundMediaPolicy`. Defaults to a
            permissive-but-denylisted policy when omitted.

    Returns:
        The resolved, symlink-free absolute path string, safe to upload.

    Raises:
        MediaDeliveryError: when the path is missing, not a regular file,
            over the size cap, on the denylist, or rejected by strict mode.
    """
    policy = policy or OutboundMediaPolicy()

    if not isinstance(path, str) or not path.strip():
        raise MediaDeliveryError("Empty media path")

    # URLs are not local files; the outbound path guard only governs local
    # filesystem reads. Callers that support remote media handle it separately.
    if path.startswith("http://") or path.startswith("https://"):
        raise MediaDeliveryError(
            f"Refusing to deliver non-local media reference: {path!r}"
        )

    resolved = _resolved(path)

    # Denylist: system dirs (absolute) and sensitive home subdirs. Checked
    # against the resolved path so symlinks/`..` cannot bypass it.
    for prefix in _DENY_PREFIXES:
        if _is_within(resolved, Path(prefix)):
            raise MediaDeliveryError(
                f"Refusing to deliver from protected location: {prefix}"
            )
    home = Path.home().resolve(strict=False)
    for sub in _DENY_HOME_SUBDIRS:
        if _is_within(resolved, home / sub):
            raise MediaDeliveryError(
                f"Refusing to deliver from protected location: ~/{sub}"
            )

    if not resolved.exists():
        raise MediaDeliveryError(f"Media path not found: {path!r}")
    if not resolved.is_file():
        raise MediaDeliveryError(f"Media path is not a regular file: {path!r}")

    if policy.max_bytes and policy.max_bytes > 0:
        try:
            size = resolved.stat().st_size
        except OSError as e:
            raise MediaDeliveryError(f"Cannot stat media path: {e}")
        if size > policy.max_bytes:
            raise MediaDeliveryError(
                f"Media file exceeds {policy.max_bytes} bytes ({size})"
            )

    if policy.strict:
        if not _passes_strict(resolved, policy):
            raise MediaDeliveryError(
                "Media path rejected by strict policy: not under an allowed "
                "root and not recently produced"
            )

    return str(resolved)


def _passes_strict(resolved: Path, policy: OutboundMediaPolicy) -> bool:
    """Strict-mode admission: allowlisted root OR recent-mtime window."""
    for root in policy.allow_roots:
        try:
            root_path = Path(root).expanduser().resolve(strict=False)
        except Exception:
            continue
        if _is_within(resolved, root_path):
            return True

    if policy.recent_mtime_seconds and policy.recent_mtime_seconds > 0:
        try:
            import time

            age = time.time() - resolved.stat().st_mtime
        except OSError:
            return False
        if 0 <= age <= policy.recent_mtime_seconds:
            return True

    return False


# Image extensions a platform may prefer to send inline (photo) vs. as a file.
_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}


def _is_image(path: str) -> bool:
    return os.path.splitext(path.lower())[1] in _IMAGE_EXTS


async def deliver_media_to_adapter(
    adapter: Any,
    channel_id: str,
    path: str,
    *,
    caption: Optional[str] = None,
) -> bool:
    """Upload a validated local ``path`` through a live platform ``adapter``.

    Routes through whichever upload primitive the adapter exposes, in order of
    preference, so each transport attaches files natively:

    * a purpose-built ``send_media(channel_id, path, caption=...)`` if present;
    * Telegram's ``_application.bot.send_photo`` / ``send_document``;
    * Slack's ``_client.files_upload_v2``;
    * Discord's ``_client.get_channel(...).send(file=...)``.

    Returns ``True`` when an upload primitive accepted the file, ``False`` when
    the adapter exposes no way to attach files (caller reports text-only
    delivery rather than misleading the model).
    """
    # 1) Adapter-native hook (future adapters / tests can implement this).
    send_media = getattr(adapter, "send_media", None)
    if callable(send_media):
        try:
            await send_media(channel_id, path, caption=caption)
            return True
        except TypeError:
            await send_media(channel_id, path)
            return True

    platform = (getattr(adapter, "platform", "") or "").lower()
    filename = os.path.basename(path)

    # 2) Telegram (python-telegram-bot).
    application = getattr(adapter, "_application", None)
    if application is not None and getattr(application, "bot", None) is not None:
        bot = application.bot
        with open(path, "rb") as fh:
            if _is_image(path) and hasattr(bot, "send_photo"):
                await bot.send_photo(
                    chat_id=int(channel_id), photo=fh, caption=caption or None
                )
            else:
                await bot.send_document(
                    chat_id=int(channel_id), document=fh, caption=caption or None
                )
        return True

    # 3) Slack (slack_sdk AsyncWebClient).
    client = getattr(adapter, "_client", None)
    if client is not None and hasattr(client, "files_upload_v2"):
        await client.files_upload_v2(
            channel=channel_id,
            file=path,
            title=filename,
            initial_comment=caption or None,
        )
        return True

    # 4) Discord (discord.py).
    if client is not None and hasattr(client, "get_channel"):
        try:
            import discord  # type: ignore

            channel = client.get_channel(int(channel_id))
            if channel is not None:
                await channel.send(
                    content=caption or None, file=discord.File(path)
                )
                return True
        except Exception as e:  # pragma: no cover — optional dep / runtime
            logger.warning("Discord media upload failed for %s: %s", channel_id, e)
            return False

    logger.info(
        "Adapter for platform %r exposes no media-upload primitive; "
        "media not attached",
        platform or "unknown",
    )
    return False


__all__ = [
    "MediaDeliveryError",
    "OutboundMediaPolicy",
    "validate_media_delivery_path",
    "deliver_media_to_adapter",
]
