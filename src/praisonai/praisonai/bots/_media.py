"""
Inbound media caching for gateway bots (Issue #2350).

Gateway bot adapters (Telegram/Discord/Slack/WhatsApp) receive photos,
documents, and videos from users. The core ``Agent`` already supports
vision via ``agent.chat(prompt, attachments=[...])``, but adapters used
to discard inbound media (WhatsApp even substituted literal placeholder
strings like ``"[Image received]"``).

This module provides a single shared helper, :func:`cache_inbound_media`,
that each adapter calls on an inbound media event to obtain a validated
local file path it can thread through ``BotSessionManager.chat(..., attachments=[...])``.

Safety properties:

- **Size cap** — bytes (or downloads) over ``max_bytes`` are rejected.
- **SSRF-safe URL fetch** — only ``http``/``https`` URLs are fetched, and
  the resolved host must not be a private/loopback/link-local address.
- **Content-type / magic-byte validation** — the leading bytes are sniffed
  so a renamed/disguised payload of the wrong kind is rejected.

The helper is intentionally dependency-light: it uses ``urllib`` from the
stdlib for fetching so no optional dependency is required.
"""

from __future__ import annotations

import ipaddress
import logging
import os
import socket
import tempfile
from typing import Optional
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# Default inbound media size cap (bytes). 20 MiB matches typical messaging
# platform attachment limits and keeps a disguised payload from filling disk.
DEFAULT_MAX_INBOUND_MEDIA_BYTES = 20 * 1024 * 1024

# Magic-byte signatures keyed by media kind. Each entry is a list of
# (offset, signature_bytes) tuples; a match on any tuple validates the kind.
# RIFF-based formats (WEBP/AVI/WAVE) share the leading ``RIFF`` magic, so a
# bare ``RIFF`` would let a WAV pass the image validator and be cached as
# ``.jpg``. They are validated separately in :func:`_matches_kind` by also
# checking the container tag at offset 8 (see ``_RIFF_TAG``).
_MAGIC = {
    "image": [
        (0, b"\xff\xd8\xff"),          # JPEG
        (0, b"\x89PNG\r\n\x1a\n"),     # PNG
        (0, b"GIF87a"),                # GIF
        (0, b"GIF89a"),                # GIF
        (0, b"BM"),                    # BMP
        (4, b"ftypheic"),              # HEIC
        (4, b"ftypheif"),              # HEIF
    ],
    "video": [
        (4, b"ftyp"),                  # MP4 / MOV / M4V family
        (0, b"\x1a\x45\xdf\xa3"),     # Matroska / WEBM
        (0, b"FLV"),                   # FLV
    ],
    "audio": [
        (0, b"ID3"),                   # MP3 w/ ID3
        (0, b"\xff\xfb"),             # MP3 frame
        (0, b"\xff\xf3"),             # MP3 frame
        (0, b"\xff\xf2"),             # MP3 frame
        (0, b"OggS"),                  # OGG / OPUS
        (4, b"ftyp"),                  # M4A / AAC in MP4 container
        (0, b"fLaC"),                  # FLAC
    ],
}

# RIFF container tags (bytes 8-12) accepted per kind. A bare ``RIFF`` header
# is ambiguous across WEBP/AVI/WAVE; requiring the tag keeps each kind from
# accepting another's payload.
_RIFF_TAG = {
    "image": b"WEBP",
    "video": b"AVI ",
    "audio": b"WAVE",
}

# Default file extensions per kind, used when writing the cached file so the
# core agent's vision path (which sniffs by extension) recognises it.
_DEFAULT_EXT = {
    "image": ".jpg",
    "video": ".mp4",
    "audio": ".ogg",
    "document": ".bin",
}


class InboundMediaError(Exception):
    """Raised when inbound media fails validation (size/type/SSRF)."""


def _matches_kind(data: bytes, kind: str) -> bool:
    """Return True if ``data`` magic bytes match ``kind`` (or kind unchecked)."""
    signatures = _MAGIC.get(kind)
    if signatures is None:
        # Unknown kind (e.g. "document"): no magic-byte gate.
        return True
    for offset, sig in signatures:
        if data[offset:offset + len(sig)] == sig:
            return True
    # RIFF families (WEBP/AVI/WAVE) share the leading magic; require the
    # container tag at offset 8 so a WAV cannot pass as an image, etc.
    riff_tag = _RIFF_TAG.get(kind)
    if riff_tag is not None and data[0:4] == b"RIFF" and data[8:12] == riff_tag:
        return True
    return False


def _is_safe_url(url: str) -> bool:
    """Return True only for http(s) URLs whose host is a public address.

    Blocks SSRF vectors: non-http(s) schemes, and hosts that resolve to
    loopback/private/link-local/reserved IP ranges.
    """
    try:
        parsed = urlparse(url)
    except Exception:
        return False
    if parsed.scheme not in ("http", "https"):
        return False
    host = parsed.hostname
    if not host:
        return False
    try:
        infos = socket.getaddrinfo(host, None)
    except Exception as e:
        logger.warning("Inbound media URL host resolution failed: %s", e)
        return False
    for info in infos:
        addr = info[4][0]
        try:
            ip = ipaddress.ip_address(addr)
        except ValueError:
            return False
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
            or ip.is_unspecified
        ):
            return False
    return True


class _SafeRedirectHandler:
    """Re-validate every redirect target so SSRF cannot be reached via 3xx."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not _is_safe_url(newurl):
            raise InboundMediaError(
                f"Refusing to follow inbound media redirect to unsafe URL: {newurl!r}"
            )
        import urllib.request
        return urllib.request.HTTPRedirectHandler.redirect_request(
            self, req, fp, code, msg, headers, newurl
        )


def _fetch_url(url: str, max_bytes: int) -> bytes:
    """Fetch ``url`` with an SSRF guard and hard size cap. Returns bytes.

    The initial URL is vetted by :func:`_is_safe_url`, and every redirect
    target is re-vetted so a public URL cannot bounce to a private host.
    """
    if not _is_safe_url(url):
        raise InboundMediaError(f"Refusing to fetch unsafe inbound media URL: {url!r}")
    import urllib.request

    class _Handler(_SafeRedirectHandler, urllib.request.HTTPRedirectHandler):
        pass

    opener = urllib.request.build_opener(_Handler())
    req = urllib.request.Request(url, headers={"User-Agent": "PraisonAI-Bot"})
    with opener.open(req, timeout=30) as resp:  # noqa: S310 - guarded above
        # Reject oversize up front when the server declares a length.
        declared = resp.headers.get("Content-Length")
        if declared is not None:
            try:
                if int(declared) > max_bytes:
                    raise InboundMediaError(
                        f"Inbound media exceeds {max_bytes} bytes (declared {declared})"
                    )
            except ValueError:
                pass
        # Read one byte past the cap so we can detect overflow without
        # streaming the whole payload into memory.
        data = resp.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise InboundMediaError(f"Inbound media exceeds {max_bytes} bytes")
    return data


def cache_inbound_media(
    data_or_path_or_url,
    *,
    kind: str = "image",
    max_bytes: Optional[int] = None,
    filename: Optional[str] = None,
) -> str:
    """Validate inbound media and return a local file path for the agent.

    Args:
        data_or_path_or_url: One of
            - ``bytes`` already downloaded by the adapter,
            - a local filesystem path (``str``) the adapter already wrote,
            - an ``http(s)`` URL (``str``) to fetch (SSRF-guarded).
        kind: ``"image"``, ``"video"``, ``"audio"`` or ``"document"``.
            Drives magic-byte validation and the cached file extension.
        max_bytes: Hard size cap. Defaults to
            :data:`DEFAULT_MAX_INBOUND_MEDIA_BYTES`.
        filename: Optional original filename, used to preserve a sensible
            extension on the cached file.

    Returns:
        Absolute path to a validated cached file under the system temp dir.

    Raises:
        InboundMediaError: when size, type, or URL validation fails.
    """
    cap = max_bytes if (max_bytes and max_bytes > 0) else DEFAULT_MAX_INBOUND_MEDIA_BYTES

    data: bytes
    if isinstance(data_or_path_or_url, bytes):
        if len(data_or_path_or_url) > cap:
            raise InboundMediaError(f"Inbound media exceeds {cap} bytes")
        data = data_or_path_or_url
    elif isinstance(data_or_path_or_url, str):
        value = data_or_path_or_url
        if value.startswith("http://") or value.startswith("https://"):
            data = _fetch_url(value, cap)
        else:
            # Treat as a local path the adapter already downloaded.
            if not os.path.exists(value):
                raise InboundMediaError(f"Inbound media path not found: {value!r}")
            size = os.path.getsize(value)
            if size > cap:
                raise InboundMediaError(f"Inbound media exceeds {cap} bytes")
            with open(value, "rb") as f:
                data = f.read()
            if filename is None:
                filename = os.path.basename(value)
    else:
        raise InboundMediaError(
            f"Unsupported inbound media input type: {type(data_or_path_or_url).__name__}"
        )

    if not data:
        raise InboundMediaError("Inbound media is empty")

    if not _matches_kind(data, kind):
        raise InboundMediaError(
            f"Inbound media failed {kind!r} content-type validation"
        )

    # Choose an extension that the agent's vision path recognises.
    ext = None
    if filename:
        _, ext = os.path.splitext(filename)
    if not ext:
        ext = _DEFAULT_EXT.get(kind, ".bin")

    fd, path = tempfile.mkstemp(prefix="inbound_media_", suffix=ext)
    try:
        with os.fdopen(fd, "wb") as out:
            out.write(data)
    except Exception:
        try:
            os.remove(path)
        except OSError:
            pass
        raise
    return path


def resolve_max_inbound_media_bytes(config) -> int:
    """Resolve the inbound-media size cap for a runtime bot config.

    The core ``BotConfig`` dataclass has no ``max_inbound_media_bytes``
    field, so an operator-supplied value (including ``0`` to disable) is
    carried through its ``metadata`` passthrough dict. Resolution order:

    1. ``config.metadata["max_inbound_media_bytes"]`` (operator override),
    2. a direct ``config.max_inbound_media_bytes`` attribute (schema-backed
       configs), then
    3. :data:`DEFAULT_MAX_INBOUND_MEDIA_BYTES` (enabled-by-default).

    Returns the resolved cap. ``0`` (or negative) means inbound media is
    disabled and callers should skip download/caching.
    """
    metadata = getattr(config, "metadata", None)
    if isinstance(metadata, dict) and "max_inbound_media_bytes" in metadata:
        try:
            return int(metadata["max_inbound_media_bytes"])
        except (TypeError, ValueError):
            pass
    value = getattr(config, "max_inbound_media_bytes", None)
    if value is None:
        return DEFAULT_MAX_INBOUND_MEDIA_BYTES
    try:
        return int(value)
    except (TypeError, ValueError):
        return DEFAULT_MAX_INBOUND_MEDIA_BYTES
