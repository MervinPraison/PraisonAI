"""
Encoding-safe symbol helpers for console output.

On some consoles (e.g. Windows default cp1252) writing decorative Unicode
glyphs such as ``▸`` (U+25B8) raises ``UnicodeEncodeError``. These helpers
detect whether the target stream can encode a symbol and provide an ASCII
fallback so progress/status output never crashes the agent loop.

This mirrors the ``_can_encode_unicode()`` fallback used by the doctor
formatter, exposed here as a shared utility for the output package.
"""

import sys
from typing import Optional, TextIO

# Common decorative glyphs mapped to safe ASCII fallbacks.
_ASCII_FALLBACKS = {
    "\u25b8": ">",   # ▸ black right-pointing small triangle
    "\u25b6": ">",   # ▶ black right-pointing triangle
    "\u25c0": "<",   # ◀ black left-pointing triangle
    "\u2192": "->",  # → rightwards arrow
    "\u2190": "<-",  # ← leftwards arrow
    "\u2713": "v",   # ✓ check mark
    "\u2717": "x",   # ✗ ballot x
    "\u2714": "v",   # ✔ heavy check mark
    "\u2718": "x",   # ✘ heavy ballot x
    "\u2500": "-",   # ─ box drawings light horizontal
    "\u2502": "|",   # │ box drawings light vertical
    "\u2514": "+",   # └ box drawings light up and right
    "\u2500\u2500": "--",
    "\U0001f4ca": "[metrics]",  # 📊 bar chart
}


def can_encode(stream: Optional[TextIO], text: str) -> bool:
    """Return True if ``text`` can be encoded by ``stream``'s encoding."""
    encoding = getattr(stream, "encoding", None) or getattr(sys.stdout, "encoding", None) or "ascii"
    if encoding.lower() in ("utf-8", "utf8"):
        return True
    try:
        text.encode(encoding, errors="strict")
        return True
    except (UnicodeEncodeError, LookupError, TypeError):
        return False


def safe_symbol(unicode_symbol: str, ascii_fallback: Optional[str] = None,
                stream: Optional[TextIO] = None) -> str:
    """
    Return ``unicode_symbol`` if the stream can encode it, else an ASCII
    fallback. When no explicit fallback is given, a sensible default is used.
    """
    target = stream if stream is not None else sys.stdout
    if can_encode(target, unicode_symbol):
        return unicode_symbol
    if ascii_fallback is not None:
        return ascii_fallback
    return _ASCII_FALLBACKS.get(unicode_symbol, "")


def safe_text(text: str, stream: Optional[TextIO] = None) -> str:
    """
    Return ``text`` with any unencodable decorative glyphs replaced by ASCII
    fallbacks so it can be printed without raising ``UnicodeEncodeError``.
    """
    target = stream if stream is not None else sys.stdout
    if can_encode(target, text):
        return text
    result = text
    for glyph, fallback in _ASCII_FALLBACKS.items():
        if glyph in result:
            result = result.replace(glyph, fallback)
    if can_encode(target, result):
        return result
    # Last resort: drop any remaining unencodable characters so printing
    # never raises UnicodeEncodeError on legacy consoles.
    encoding = getattr(target, "encoding", None) or getattr(sys.stdout, "encoding", None) or "ascii"
    try:
        return result.encode(encoding, errors="replace").decode(encoding, errors="replace")
    except (LookupError, TypeError):
        return result.encode("ascii", errors="replace").decode("ascii")


__all__ = ["can_encode", "safe_symbol", "safe_text"]
