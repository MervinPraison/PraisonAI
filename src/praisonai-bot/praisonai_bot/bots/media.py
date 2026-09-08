"""
Media parsing utilities for bot responses.

Parses MEDIA: protocol from agent responses to extract audio/image paths.
Similar to moltbot's splitMediaFromOutput() pattern.
"""

import logging
import os
import re
from typing import Dict, List, Any, Optional

logger = logging.getLogger(__name__)

# Regex to match MEDIA:/path lines
MEDIA_REGEX = re.compile(r"^MEDIA:(.+)$", re.MULTILINE)

# Voice bubble control tag (Telegram)
VOICE_TAG = "[[audio_as_voice]]"


def split_media_from_output(text: str) -> Dict[str, Any]:
    """
    Extract MEDIA: paths from agent response text.
    
    Parses lines like:
        MEDIA:/tmp/tts_abc123.mp3
        [[audio_as_voice]]
    
    Args:
        text: Raw agent response text
        
    Returns:
        Dict with:
            - text: Cleaned text without MEDIA: lines
            - media_urls: List of extracted file paths
            - audio_as_voice: True if [[audio_as_voice]] tag present
            
    Example:
        >>> split_media_from_output("Hello\\nMEDIA:/tmp/audio.mp3")
        {"text": "Hello", "media_urls": ["/tmp/audio.mp3"], "audio_as_voice": False}
    """
    if not text:
        return {"text": "", "media_urls": [], "audio_as_voice": False}
    
    # Check for voice tag
    audio_as_voice = VOICE_TAG in text
    clean = text.replace(VOICE_TAG, "")
    
    # Extract media paths
    media_urls: List[str] = []
    for path in _iter_media_paths(clean):
        # Validate path exists or is URL
        if path and (os.path.exists(path) or path.startswith("http")):
            media_urls.append(path)
    
    return {
        "text": _strip_media_lines(clean),
        "media_urls": media_urls,
        "audio_as_voice": audio_as_voice,
    }


def _iter_media_paths(clean: str):
    """Yield the unquoted path of each ``MEDIA:`` directive in ``clean``."""
    for match in MEDIA_REGEX.finditer(clean):
        path = match.group(1).strip()
        # Remove quotes if present
        if path.startswith('"') and path.endswith('"'):
            path = path[1:-1]
        elif path.startswith("'") and path.endswith("'"):
            path = path[1:-1]
        yield path


def _strip_media_lines(clean: str) -> str:
    """Remove ``MEDIA:`` lines and collapse the excess blank runs they leave.

    NOTE: only *excess* blank runs left behind by stripped MEDIA lines are
    collapsed. Legitimate blank lines are load-bearing on the outbound path —
    they are the paragraph separators for chunking and the only visual break in
    plain-text replies — so a single blank line between blocks is preserved
    (Issue #4319).
    """
    clean = MEDIA_REGEX.sub("", clean)
    clean = re.sub(r"\n[ \t]*\n(?:[ \t]*\n)+", "\n\n", clean)
    return clean.strip()


async def split_media_from_output_async(
    text: str,
    *,
    remote_resolver: Optional[Any] = None,
) -> Dict[str, Any]:
    """Remote-sandbox-aware variant of :func:`split_media_from_output`.

    Identical to the synchronous version for local paths and URLs, but when a
    ``MEDIA:`` path is neither local nor an ``http(s)`` URL **and** an active
    sandbox ``remote_resolver`` owns it (see
    :class:`praisonaiagents.gateway.RemoteMediaResolver`), the artifact is
    fetched out of the sandbox into a gateway-local delivery cache so it can be
    delivered instead of being silently dropped (Issue #4951).

    Fail-open and backward-compatible: with ``remote_resolver=None`` the result
    is byte-for-byte what :func:`split_media_from_output` returns; a fetch
    failure degrades to the historical silent-drop plus an operator-visible
    warning, never a crash.

    Args:
        text: Raw agent response text.
        remote_resolver: Optional resolver satisfying ``RemoteMediaResolver``
            (``owns_path`` + async ``fetch_to_local``) for the current turn's
            sandbox backend.

    Returns:
        Same shape as :func:`split_media_from_output`.
    """
    if not text:
        return {"text": "", "media_urls": [], "audio_as_voice": False}

    audio_as_voice = VOICE_TAG in text
    clean = text.replace(VOICE_TAG, "")

    media_urls: List[str] = []
    for path in _iter_media_paths(clean):
        if not path:
            continue
        if os.path.exists(path) or path.startswith("http"):
            media_urls.append(path)
            continue
        if remote_resolver is not None:
            fetched = await _fetch_remote_media(path, remote_resolver)
            if fetched is not None:
                media_urls.append(fetched)
                continue
        logger.warning(
            "Dropping undeliverable MEDIA path (not local, no remote "
            "resolver owns it): %r",
            path,
        )

    return {
        "text": _strip_media_lines(clean),
        "media_urls": media_urls,
        "audio_as_voice": audio_as_voice,
    }


async def _fetch_remote_media(path: str, remote_resolver: Any) -> Optional[str]:
    """Fetch a sandbox-local ``path`` to a re-guarded local path, or None.

    Reuses the backend's existing download primitive via the resolver's
    ``fetch_to_local`` and re-screens the fetched copy through the outbound
    exfiltration guard. Any failure (resolver disowns the path, download error,
    guard rejection) returns ``None`` so the caller degrades to the historical
    silent-drop-plus-warning rather than crashing the reply.
    """
    try:
        owns = remote_resolver.owns_path(path)
    except Exception:
        logger.warning(
            "Remote media resolver owns_path failed for %r", path, exc_info=True
        )
        return None
    if not owns:
        return None
    try:
        local = await remote_resolver.fetch_to_local(path)
    except Exception:
        logger.warning(
            "Remote media fetch failed for %r; dropping attachment",
            path,
            exc_info=True,
        )
        return None
    if not local:
        return None
    try:
        from ._outbound_media import validate_media_delivery_path

        return validate_media_delivery_path(local)
    except Exception:
        logger.warning(
            "Fetched remote media %r rejected by delivery guard; dropping",
            local,
            exc_info=True,
        )
        return None


def is_audio_file(path: str) -> bool:
    """Check if file path is an audio file by extension."""
    audio_extensions = {".mp3", ".wav", ".ogg", ".opus", ".m4a", ".aac", ".flac"}
    return os.path.splitext(path.lower())[1] in audio_extensions
