"""
Shared text-to-speech (TTS) / voice-reply helpers for gateway bots (Issue #3623).

Inbound speech-to-text is a first-class, on-by-default, cross-platform gateway
feature (:mod:`_stt`). This module supplies the missing *outbound* counterpart:
a config-driven "reply in voice" path that mirrors ``stt`` exactly, so a bot can
speak back on any adapter that exposes a voice-send primitive — without the agent
hand-building ``MEDIA:/path [[audio_as_voice]]`` markers.

Two pieces, deliberately symmetrical with :mod:`_stt`:

- :func:`resolve_tts_config` — read the operator's ``voice`` (alias ``tts``) block
  (carried through :class:`BotConfig.metadata` the same way ``stt`` is) into a
  small :class:`TtsConfig`. Off by default (opt-in), unlike ``stt``.
- :func:`synthesize_voice_reply` — synthesise the agent's final text to a local
  voice-note file via the existing ``tools.audio.tts_tool`` (which wraps the core
  ``AudioAgent.speech``), so the heavy TTS provider dependency stays in tools and
  out of core and the bot layer.

Delivery of the produced file as a *native* voice note is left to the adapter
(Telegram ``send_voice``, WhatsApp voice note, Discord/Slack audio upload) — the
same graceful-degradation contract as media delivery. The agent keeps returning
plain text; voice is a transport concern the gateway owns, exactly like STT.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Delivery modes (parallel to the STT on/off switch, but with the intuitive
# symmetry mode that only speaks back when the user spoke first):
#   "off"           — never reply in voice (default; today's behaviour).
#   "always"        — every reply is also sent as a voice note.
#   "match_inbound" — reply in voice only when the incoming message was a voice
#                     memo (the natural mirror of inbound STT).
MODE_OFF = "off"
MODE_ALWAYS = "always"
MODE_MATCH_INBOUND = "match_inbound"
_VALID_MODES = {MODE_OFF, MODE_ALWAYS, MODE_MATCH_INBOUND}


@dataclass
class TtsConfig:
    """Resolved outbound voice-reply policy for a channel.

    Attributes:
        enabled: Master switch. Off by default (opt-in), the mirror of STT's
            on-by-default inbound transcription.
        mode: ``off`` | ``always`` | ``match_inbound``. Ignored when
            ``enabled`` is ``False``.
        model: Optional TTS model override (default: ``openai/tts-1``).
        voice: Optional voice name (e.g. ``"alloy"``).
        speed: Optional speaking-rate multiplier passed through to the provider.
        format: Output audio format. ``ogg``/``opus`` are the voice-note native
            formats (default ``ogg``).
        max_chars: Skip TTS for replies longer than this many characters
            (``0`` disables the cap). Keeps very long text from being narrated.
    """

    enabled: bool = False
    mode: str = MODE_OFF
    model: Optional[str] = None
    voice: Optional[str] = None
    speed: Optional[float] = None
    format: str = "ogg"
    max_chars: int = 4000


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


def _coerce_mode(value: Any, default: str) -> str:
    """Normalise a mode string; unknown values fall back to ``default``."""
    if isinstance(value, str):
        token = value.strip().lower().replace("-", "_")
        if token in _VALID_MODES:
            return token
    return default


def _coerce_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _coerce_float(value: Any, default: Optional[float]) -> Optional[float]:
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _from_mapping(get: Any) -> TtsConfig:
    """Build a :class:`TtsConfig` from a ``get(key, default)`` accessor."""
    base = TtsConfig()
    enabled = _coerce_bool(get("enabled", base.enabled), base.enabled)
    # A bare ``mode`` other than "off" implies the operator wants voice on, so
    # honour it even if ``enabled`` was omitted — the intuitive shorthand.
    mode = _coerce_mode(get("mode", base.mode), base.mode)
    if not enabled and mode != MODE_OFF and get("enabled", None) is None:
        enabled = True
    return TtsConfig(
        enabled=enabled,
        mode=mode,
        model=get("model", base.model),
        voice=get("voice", base.voice),
        speed=_coerce_float(get("speed", base.speed), base.speed),
        format=str(get("format", base.format) or base.format),
        max_chars=_coerce_int(get("max_chars", base.max_chars), base.max_chars),
    )


def resolve_tts_config(config: Any) -> TtsConfig:
    """Resolve the effective :class:`TtsConfig` for a runtime bot config.

    The core ``BotConfig`` dataclass has no ``voice`` field, so an operator's
    ``voice`` (or ``tts``) block flows through its ``metadata`` passthrough dict
    — mirroring how ``stt`` is resolved in :func:`_stt.resolve_stt_config`.

    Resolution order:

    1. ``config.metadata["voice"]`` / ``["tts"]`` (operator override),
    2. a direct ``config.voice`` / ``config.tts`` attribute, then
    3. the off-by-default :class:`TtsConfig`.

    A bare boolean (``voice: true``) is accepted as ``{"enabled": <bool>}``.
    """
    raw: Any = None

    metadata = getattr(config, "metadata", None)
    if isinstance(metadata, dict):
        if "voice" in metadata:
            raw = metadata["voice"]
        elif "tts" in metadata:
            raw = metadata["tts"]
    if raw is None:
        raw = getattr(config, "voice", None)
    if raw is None:
        raw = getattr(config, "tts", None)

    if raw is None:
        return TtsConfig()

    if isinstance(raw, bool):
        return TtsConfig(enabled=raw, mode=MODE_ALWAYS if raw else MODE_OFF)

    if isinstance(raw, TtsConfig):
        return raw

    if isinstance(raw, dict):
        return _from_mapping(lambda k, d=None: raw.get(k, d))

    # Unknown shape (e.g. a pydantic model): read attributes defensively.
    return _from_mapping(lambda k, d=None: getattr(raw, k, d))


def should_voice_reply(cfg: TtsConfig, *, inbound_was_voice: bool) -> bool:
    """Return True if this reply should be spoken, given the resolved policy.

    Centralises the mode logic so every adapter branches identically:
    ``off`` never speaks, ``always`` always speaks, and ``match_inbound`` speaks
    only when the incoming message was itself a voice memo.
    """
    if not cfg.enabled or cfg.mode == MODE_OFF:
        return False
    if cfg.mode == MODE_MATCH_INBOUND:
        return bool(inbound_was_voice)
    return True


def synthesize_voice_reply(text: str, cfg: TtsConfig) -> Optional[str]:
    """Synthesise ``text`` to a local voice-note file, or ``None`` on skip/fail.

    Reuses ``tools.audio.tts_tool`` (which wraps the core ``AudioAgent.speech``)
    so the heavy TTS provider dependency stays in tools. Returns the path to the
    produced audio file, or ``None`` when there is nothing to say, the reply is
    too long, or synthesis is unavailable/fails — callers fall back to plain
    text rather than dropping the reply.
    """
    if not text or not text.strip():
        return None
    if cfg.max_chars and cfg.max_chars > 0 and len(text) > cfg.max_chars:
        logger.info(
            "Skipping voice reply: %d chars exceeds max_chars=%d",
            len(text),
            cfg.max_chars,
        )
        return None

    try:
        from praisonai_bot.tools.audio import tts_tool
    except Exception as e:  # pragma: no cover — optional heavy deps
        logger.warning("TTS tool unavailable: %s", e)
        return None

    try:
        result = tts_tool(
            text,
            voice=cfg.voice,
            model=cfg.model,
            output_format=cfg.format or "ogg",
            speed=cfg.speed,
        )
    except Exception as e:
        logger.error("Voice reply synthesis error: %s", e)
        return None

    if result.get("success"):
        path = result.get("audio_path")
        if path:
            logger.info("Synthesised voice reply: %s", path)
            return path
        return None

    logger.warning("TTS failed: %s", result.get("error"))
    return None


__all__ = [
    "TtsConfig",
    "MODE_OFF",
    "MODE_ALWAYS",
    "MODE_MATCH_INBOUND",
    "resolve_tts_config",
    "should_voice_reply",
    "synthesize_voice_reply",
]
