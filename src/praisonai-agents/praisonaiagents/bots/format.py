"""
Markdown dialect conversion for agent replies.

A pure, dependency-free (stdlib-only) default that finally *consumes* the
``markdown_dialect`` capability every platform adapter already declares
(:class:`~praisonaiagents.bots.protocols.PlatformCapabilities`). It turns an
agent's ordinary markdown reply into the flavour the target platform speaks so
formatting renders correctly and a reply is never dropped by a transport that
rejects unescaped special characters (e.g. Telegram's ``400 can't parse
entities``).

The single entry point is :func:`format_for_dialect`, which returns the
``(rendered_text, parse_mode)`` pair a send path needs::

    text, mode = format_for_dialect(agent_text, caps.markdown_dialect)
    await bot.send_message(chat_id, text, parse_mode=mode)

Supported dialects:

* ``"telegram_markdown_v2"`` -> MarkdownV2-escaped text, ``parse_mode="MarkdownV2"``
* ``"slack"``                -> Slack mrkdwn text,        ``parse_mode=None``
* ``"discord_markdown"``     -> passthrough (Discord speaks CommonMark),
  ``parse_mode=None``
* ``"markdown"``/unknown     -> safe plain text,          ``parse_mode=None``

This lives in core because it is the light default for a core protocol seam:
pure string work, no heavy imports, and driven by the capability contract each
adapter already advertises. Adapters call it from their send paths.
"""

from __future__ import annotations

import re
from typing import Optional, Tuple

__all__ = [
    "format_for_dialect",
    "escape_markdown_v2",
    "markdown_to_slack",
    "strip_markdown",
]

# Characters Telegram MarkdownV2 requires escaping outside entities.
# See https://core.telegram.org/bots/api#markdownv2-style
_MDV2_SPECIAL = r"_*[]()~`>#+-=|{}.!\\"
_MDV2_ESCAPE_RE = re.compile("([" + re.escape(_MDV2_SPECIAL) + "])")


def escape_markdown_v2(text: str) -> str:
    """Escape every Telegram MarkdownV2 special character in ``text``.

    This is the conservative, always-safe escape: it treats the input as plain
    text and backslash-escapes each reserved character so Telegram accepts the
    message verbatim without a ``can't parse entities`` error. Existing markup
    (``**bold**``, ``[links](url)``) is shown literally rather than reinterpreted;
    correctness (never dropping a reply) is preferred over best-effort styling.
    """
    if not text:
        return ""
    return _MDV2_ESCAPE_RE.sub(r"\\\1", text)


# Inline markdown -> Slack mrkdwn conversions (order matters: bold before italic).
_MD_BOLD_RE = re.compile(r"\*\*(.+?)\*\*", re.DOTALL)
_MD_LINK_RE = re.compile(r"\[([^\]]+)\]\((https?://[^\s)]+)\)")
_MD_HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s+(.*)$", re.MULTILINE)


def markdown_to_slack(text: str) -> str:
    """Convert common markdown to Slack ``mrkdwn``.

    Slack uses ``*bold*`` (single asterisk), ``_italic_``, ``<url|label>`` links
    and has no ``#`` headings. This maps the frequent cases and otherwise leaves
    text untouched, so a plain reply passes through unchanged.
    """
    if not text:
        return ""
    # Links: [label](url) -> <url|label>
    text = _MD_LINK_RE.sub(lambda m: f"<{m.group(2)}|{m.group(1)}>", text)
    # Bold: **x** -> *x* (do before single-asterisk handling is unnecessary here)
    text = _MD_BOLD_RE.sub(lambda m: f"*{m.group(1)}*", text)
    # Headings: "# Title" -> "*Title*" (Slack has no headings)
    text = _MD_HEADING_RE.sub(lambda m: f"*{m.group(1).strip()}*", text)
    return text


# Markdown constructs to drop when falling back to plain text.
_STRIP_LINK_RE = re.compile(r"\[([^\]]+)\]\((?:https?://[^\s)]+)\)")
_STRIP_HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s+", re.MULTILINE)
# Only unwrap *paired* emphasis/code delimiters so literal characters
# (e.g. ``svc_1``, ``*.py``, ``a*b``) are preserved rather than deleted.
_STRIP_BOLD_RE = re.compile(r"(\*\*|__)(?=\S)(.+?)(?<=\S)\1", re.DOTALL)
_STRIP_ITALIC_RE = re.compile(r"(?<![*_\w])([*_])(?=\S)(.+?)(?<=\S)\1(?![*_\w])")
_STRIP_CODE_RE = re.compile(r"`([^`]+)`")


def strip_markdown(text: str) -> str:
    """Reduce markdown to readable plain text (safe fallback).

    Unwraps *paired* emphasis/code spans and heading hashes and unwraps links
    to their label, so a reply reads cleanly on a platform whose dialect we
    don't specifically target. Unpaired or literal delimiters (``svc_1``,
    ``*.py``, ``a*b``) are left untouched so identifiers and code are never
    corrupted.
    """
    if not text:
        return ""
    text = _STRIP_LINK_RE.sub(r"\1", text)
    text = _STRIP_HEADING_RE.sub("", text)
    text = _STRIP_CODE_RE.sub(r"\1", text)
    text = _STRIP_BOLD_RE.sub(r"\2", text)
    text = _STRIP_ITALIC_RE.sub(r"\2", text)
    return text


def format_for_dialect(text: str, dialect: str) -> Tuple[str, Optional[str]]:
    """Render ``text`` for a platform's declared ``markdown_dialect``.

    Args:
        text: The agent's reply text, authored in ordinary markdown.
        dialect: The platform's ``markdown_dialect`` capability value.

    Returns:
        ``(rendered_text, parse_mode)`` — ``parse_mode`` is the value the
        transport expects (e.g. ``"MarkdownV2"`` for Telegram) or ``None`` when
        the text is already in the platform's native form / plain text.
    """
    if text is None:
        return ("", None)
    if dialect == "telegram_markdown_v2":
        return (escape_markdown_v2(text), "MarkdownV2")
    if dialect == "slack":
        return (markdown_to_slack(text), None)
    if dialect == "discord_markdown":
        return (text, None)
    # "markdown" / unknown: safe plain-text fallback.
    return (strip_markdown(text), None)
