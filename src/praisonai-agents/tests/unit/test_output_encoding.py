"""Tests for encoding-safe console output on legacy (cp1252) consoles."""

import io
import sys

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


def test_safe_text_handles_non_str_input():
    # Non-str values (e.g. None) must not raise; they are returned unchanged.
    assert safe_text(None, _Cp1252Stream()) is None
    assert safe_text(123, _Cp1252Stream()) == 123


def test_can_encode_handles_non_str_input():
    assert can_encode(_Cp1252Stream(), None) is True


def test_status_output_no_unicode_error_on_cp1252():
    stream = _Cp1252Stream()
    out = StatusOutput(file=stream, use_color=False, show_timestamps=False)
    out.llm_start(model="gpt-4o-mini")
    stream.getvalue().encode("cp1252")  # must not raise


def test_status_output_final_output_no_unicode_error_on_cp1252(monkeypatch):
    # StatusOutput.output() prints the final content to sys.stdout, so patch it.
    stdout = _Cp1252Stream()
    monkeypatch.setattr(sys, "stdout", stdout)
    out = StatusOutput(file=_Cp1252Stream(), use_color=False, show_timestamps=False)
    out.output("\u25b8 done \u2192 ok")
    stdout.getvalue().encode("cp1252")  # must not raise


def test_trace_output_no_unicode_error_on_cp1252():
    stream = _Cp1252Stream()
    out = TraceOutput(file=stream, use_color=False, show_timestamps=False)
    out.tool_start("get_weather", {"city": "Paris"})
    out.tool_end("get_weather", result="sunny", success=True)
    stream.getvalue().encode("cp1252")  # must not raise


def test_trace_output_response_no_unicode_error_on_cp1252():
    stream = _Cp1252Stream()
    out = TraceOutput(file=stream, use_color=False, show_timestamps=False)
    out.response("\u25b8 answer \u2192 ok")
    stream.getvalue().encode("cp1252")  # must not raise


def test_trace_output_response_preserves_unicode_on_utf8():
    stream = _Utf8Stream()
    out = TraceOutput(file=stream, use_color=False, show_timestamps=False)
    out.response("\u25b8 answer \u2192 ok")
    assert "\u25b8" in stream.getvalue()
