"""
Shared speech-to-text (STT) helpers for gateway bots (Issue #2721).

Inbound voice notes are a first-class gateway experience, but the transcription
plumbing used to be off by default, un-wired, and inconsistent across channels.
This module centralises the two pieces every adapter needs so Telegram, Slack
and WhatsApp all transcribe inbound audio the same way:

- :func:`resolve_stt_config` — read the operator's ``stt`` block (carried through
  :class:`BotConfig.metadata` the same way ``max_inbound_media_bytes`` is) into a
  small :class:`SttConfig` with sane, on-by-default values.
- :func:`transcribe_media_path` — transcribe a local audio file via the existing
  ``tools.audio.stt_tool`` (which wraps the core ``AudioAgent.transcribe``), so the
  heavy whisper/litellm dependency stays in tools and out of core.

The design goal is graceful degradation: when STT is disabled or transcription
fails, callers fall back to a visible placeholder (e.g. ``"[Voice message
received]"``) instead of silently dropping the user's message.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Default placeholder used when a voice note cannot be transcribed (STT off or
# failure). Keeps the turn reaching the agent instead of being dropped.
DEFAULT_VOICE_PLACEHOLDER = "[Voice message received]"


@dataclass
class SttConfig:
    """Resolved inbound speech-to-text policy for a channel.

    Attributes:
        enabled: Transcribe inbound audio. On by default (Issue #2721).
        echo_transcripts: Echo the recognised text back to the user.
        language: Optional forced language code (``"en"``, ``"es"`` …).
        model: Optional STT model override (default: ``openai/whisper-1``).
    """

    enabled: bool = True
    echo_transcripts: bool = False
    language: Optional[str] = None
    model: Optional[str] = None


# String tokens treated as booleans for text-backed config (YAML/env).
_TRUE_TOKENS = {"true", "1", "yes", "on"}
_FALSE_TOKENS = {"false", "0", "no", "off"}


def _coerce_bool(value: Any, default: bool) -> bool:
    """Coerce ``value`` to a bool without ``bool("false") is True`` surprises."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        token = value.strip().lower()
        if token in _TRUE_TOKENS:
            return True
        if token in _FALSE_TOKENS:
            return False
    return default


def resolve_stt_config(config: Any) -> SttConfig:
    """Resolve the effective :class:`SttConfig` for a runtime bot config.

    The core ``BotConfig`` dataclass has no ``stt`` field, so an operator's
    ``stt`` block (from YAML/CLI) is carried through its ``metadata`` passthrough
    dict — mirroring how ``max_inbound_media_bytes`` flows in ``_media.py``.

    Resolution order:

    1. ``config.metadata["stt"]`` (operator override; dict or bool),
    2. a direct ``config.stt`` attribute (schema-backed configs), then
    3. the on-by-default :class:`SttConfig`.

    A bare boolean (``stt: true`` / ``stt: false``) is accepted as a shorthand
    for ``{"enabled": <bool>}``.
    """
    raw: Any = None

    metadata = getattr(config, "metadata", None)
    if isinstance(metadata, dict) and "stt" in metadata:
        raw = metadata["stt"]
    if raw is None:
        raw = getattr(config, "stt", None)

    if raw is None:
        return SttConfig()

    if isinstance(raw, bool):
        return SttConfig(enabled=raw)

    if isinstance(raw, SttConfig):
        return raw

    if isinstance(raw, dict):
        base = SttConfig()
        return SttConfig(
            enabled=_coerce_bool(raw.get("enabled", base.enabled), base.enabled),
            echo_transcripts=_coerce_bool(
                raw.get("echo_transcripts", base.echo_transcripts),
                base.echo_transcripts,
            ),
            language=raw.get("language", base.language),
            model=raw.get("model", base.model),
        )

    # Unknown shape (e.g. a pydantic model): read attributes defensively.
    base = SttConfig()
    return SttConfig(
        enabled=_coerce_bool(getattr(raw, "enabled", base.enabled), base.enabled),
        echo_transcripts=_coerce_bool(
            getattr(raw, "echo_transcripts", base.echo_transcripts),
            base.echo_transcripts,
        ),
        language=getattr(raw, "language", base.language),
        model=getattr(raw, "model", base.model),
    )


def transcribe_media_path(
    audio_path: str,
    *,
    language: Optional[str] = None,
    model: Optional[str] = None,
) -> Optional[str]:
    """Transcribe a local audio file to text via the shared STT tool.

    Reuses ``tools.audio.stt_tool`` (which wraps the core
    ``AudioAgent.transcribe``) so the heavy whisper/litellm dependency stays in
    tools. Returns the transcript, or ``None`` when transcription is
    unavailable or fails — callers should fall back to a placeholder rather than
    drop the message.
    """
    if not audio_path:
        return None
    try:
        from praisonai_bot.tools.audio import stt_tool
    except Exception as e:  # pragma: no cover — optional heavy deps
        logger.warning("STT tool unavailable: %s", e)
        return None

    try:
        result = stt_tool(audio_path, language=language, model=model)
    except Exception as e:
        logger.error("Audio transcription error: %s", e)
        return None

    if result.get("success"):
        text = (result.get("text") or "").strip()
        if text:
            logger.info("Transcribed voice message: %s...", text[:50])
            return text
        return None

    logger.warning("STT failed: %s", result.get("error"))
    return None


__all__ = [
    "SttConfig",
    "DEFAULT_VOICE_PLACEHOLDER",
    "resolve_stt_config",
    "transcribe_media_path",
]
