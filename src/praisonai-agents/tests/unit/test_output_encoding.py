"""Tests for encoding-safe console output on legacy (cp1252) consoles."""

import io

from praisonaiagents.output.encoding import can_encode, safe_symbol, safe_text
from praisonaiagents.output.status import StatusOutput
from praisonaiagents.output.trace import TraceOutput


class _Cp1252Stream(io.StringIO):
    """A text stream that reports a cp1252 encoding."""

    encoding = "cp1252"


class _Utf8Stream(io.StringIO):
    """A text stream that reports a utf-8 encoding."""

    encoding = "utf-8"


def test_can_encode_utf8():
    assert can_encode(_Utf8Stream(), "\u25b8") is True


def test_can_encode_cp1252_rejects_bullet():
    assert can_encode(_Cp1252Stream(), "\u25b8") is False


def test_safe_symbol_falls_back_on_cp1252():
    assert safe_symbol("\u25b8", ">", _Cp1252Stream()) == ">"


def test_safe_symbol_default_fallback():
    assert safe_symbol("\u25b8", stream=_Cp1252Stream()) == ">"


def test_safe_symbol_keeps_unicode_on_utf8():
    assert safe_symbol("\u25b8", ">", _Utf8Stream()) == "\u25b8"


def test_safe_text_replaces_glyphs_on_cp1252():
    result = safe_text("\u25b8 AI \u2192 thinking...", _Cp1252Stream())
    assert "\u25b8" not in result
    result.encode("cp1252")  # must not raise


def test_status_output_no_unicode_error_on_cp1252():
    stream = _Cp1252Stream()
    out = StatusOutput(file=stream, use_color=False, show_timestamps=False)
    out.llm_start(model="gpt-4o-mini")
    stream.getvalue().encode("cp1252")  # must not raise


def test_trace_output_no_unicode_error_on_cp1252():
    stream = _Cp1252Stream()
    out = TraceOutput(file=stream, use_color=False, show_timestamps=False)
    out.tool_start("get_weather", {"city": "Paris"})
    out.tool_end("get_weather", result="sunny", success=True)
    stream.getvalue().encode("cp1252")  # must not raise
