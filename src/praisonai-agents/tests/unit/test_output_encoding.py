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


def test_status_output_rich_color_llm_start_no_unicode_error_on_cp1252():
    # Production default is use_color=True, which routes through the Rich
    # branch of _emit_text. This is the live `praisonai run` crash path
    # (issue #2603) that earlier use_color=False tests never exercised.
    stream = _Cp1252Stream()
    out = StatusOutput(file=stream, use_color=True, show_timestamps=False)
    out.llm_start(model="gpt-4o-mini")  # emits "▸ AI → thinking..."
    stream.getvalue().encode("cp1252")  # must not raise
    assert "\u25b8" not in stream.getvalue()


def test_status_output_rich_color_agent_lifecycle_no_unicode_error_on_cp1252():
    # agent_start/agent_end emit ▶ (U+25B6) / ◀ (U+25C0) via the Rich branch.
    stream = _Cp1252Stream()
    out = StatusOutput(file=stream, use_color=True, show_timestamps=False)
    out.agent_start("assistant")
    out.agent_end("assistant", duration_ms=12.0)
    stream.getvalue().encode("cp1252")  # must not raise


def test_status_output_rich_color_tool_end_no_unicode_error_on_cp1252():
    stream = _Cp1252Stream()
    out = StatusOutput(file=stream, use_color=True, show_timestamps=False)
    out.tool_start("get_weather", {"city": "Paris"})
    out.tool_end("get_weather", status="error", error_message="boom")
    stream.getvalue().encode("cp1252")  # must not raise


def test_status_output_rich_color_preserves_unicode_on_utf8():
    stream = _Utf8Stream()
    out = StatusOutput(file=stream, use_color=True, show_timestamps=False)
    out.llm_start(model="gpt-4o-mini")
    assert "\u25b8" in stream.getvalue()  # glyph preserved on utf-8


def test_status_output_final_output_no_unicode_error_on_cp1252(monkeypatch):
    # StatusOutput.output() prints the final content to sys.stdout, so patch it.
    stdout = _Cp1252Stream()
    monkeypatch.setattr(sys, "stdout", stdout)
    out = StatusOutput(file=_Cp1252Stream(), use_color=False, show_timestamps=False)
    out.output("\u25b8 done \u2192 ok")
    stdout.getvalue().encode("cp1252")  # must not raise


def test_editor_llm_indicator_no_unicode_error_on_cp1252():
    # EditorDisplay.llm_indicator emits "▸ Thinking..." via a Rich console
    # (issue #2603 latent path). It must not crash on a cp1252 stream.
    from rich.console import Console
    from praisonaiagents.output.editor import EditorOutput

    stream = io.TextIOWrapper(io.BytesIO(), encoding="cp1252", errors="strict")
    console = Console(file=stream, force_terminal=True)
    out = EditorOutput(console=console, use_rich=True)
    out.llm_indicator("thinking")
    stream.flush()  # must not raise UnicodeEncodeError


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


# ---------------------------------------------------------------------------
# main.py Rich display path (praisonai run) — reproduces issue #2569.
# Rich's legacy Windows renderer encodes with the terminal encoding using
# strict error handling, so decorative glyphs (▸ U+25B8, ⚠ U+26A0) crash the
# agent loop. These tests drive the real Rich Console against a cp1252-backed
# stream and assert the display helpers degrade gracefully.
# ---------------------------------------------------------------------------


def _make_console(encoding="cp1252", force_terminal=True):
    """Build a Rich Console whose file strictly encodes with ``encoding``."""
    from rich.console import Console

    stream = io.TextIOWrapper(io.BytesIO(), encoding=encoding, errors="strict")
    return Console(file=stream, force_terminal=force_terminal), stream


def _cp1252_console(force_terminal=True):
    """Build a Rich Console whose file strictly encodes as cp1252."""
    return _make_console("cp1252", force_terminal)


def test_rich_console_reproduces_cp1252_error():
    # Sanity check: a raw Rich print of ▸ DOES raise on cp1252 (the bug).
    console, _ = _cp1252_console()
    import pytest

    with pytest.raises(UnicodeEncodeError):
        console.print("[bold]\u25b8[/] test")


def test_display_tool_call_no_unicode_error_on_cp1252():
    from praisonaiagents.main import display_tool_call

    console, stream = _cp1252_console()
    # Legacy inline format uses the ▸ (U+25B8) prefix directly.
    display_tool_call("running search tool", console=console)
    stream.flush()  # must not raise UnicodeEncodeError


def test_display_tool_call_structured_no_unicode_error_on_cp1252():
    from praisonaiagents.main import display_tool_call

    console, stream = _cp1252_console()
    display_tool_call(
        "search",
        console=console,
        tool_name="search",
        tool_input={"q": "weather"},
        tool_output="sunny",
        elapsed_time=0.5,
        success=True,
    )
    stream.flush()  # must not raise UnicodeEncodeError


def test_display_error_no_unicode_error_on_cp1252():
    from praisonaiagents.main import display_error

    console, stream = _cp1252_console()
    # Panel title "⚠ Error" (U+26A0) previously crashed on cp1252.
    display_error("something went wrong", console=console)
    stream.flush()  # must not raise UnicodeEncodeError


def test_display_interaction_no_unicode_error_on_cp1252():
    from praisonaiagents.main import display_interaction

    console, stream = _cp1252_console()
    display_interaction(
        "\u25b8 question", "\u25b8 answer", markdown=False, console=console
    )
    stream.flush()  # must not raise UnicodeEncodeError


def test_display_tool_call_preserves_unicode_on_utf8():
    from praisonaiagents.main import display_tool_call

    console, stream = _make_console("utf-8")
    display_tool_call("running search", console=console)
    stream.flush()
    stream.seek(0)
    assert "\u25b8" in stream.buffer.getvalue().decode("utf-8")


def test_display_interaction_markdown_no_unicode_error_on_cp1252():
    # markdown=True routes the response through Panel.fit(Markdown(...)),
    # whose body previously stayed unsanitized and dropped the LLM response.
    from praisonaiagents.main import display_interaction

    console, stream = _cp1252_console()
    display_interaction(
        "the question",
        "the answer \u25b8 with a decorative glyph \u2192 here",
        markdown=True,
        console=console,
    )
    stream.flush()  # must not raise UnicodeEncodeError
    stream.seek(0)
    rendered = stream.buffer.getvalue().decode("cp1252")
    # The response text must survive the fallback, not be dropped.
    assert "answer" in rendered


def test_sanitize_markdown_rebuilds_from_safe_markup():
    from rich.markdown import Markdown
    from praisonaiagents.main import _sanitize_renderable

    md = Markdown("hello \u25b8 world")
    out = _sanitize_renderable(md, _Cp1252Stream())
    assert isinstance(out, Markdown)
    assert "\u25b8" not in out.markup
    out.markup.encode("cp1252")  # must not raise


def test_safe_console_print_fallback_writes_to_console_stream():
    # The last-resort plain print must target the console's own stream,
    # not the process-wide sys.stdout.
    from rich.console import Console
    from rich.markdown import Markdown
    from rich.panel import Panel
    from praisonaiagents.main import _safe_console_print

    class _StrictMarkdown(Markdown):
        # Force both Rich attempts to fail so the plain fallback runs.
        def __rich_console__(self, console, options):
            raise UnicodeEncodeError("cp1252", "\u25b8", 0, 1, "boom")

    stream = _Cp1252Stream()
    console = Console(file=stream, force_terminal=True)
    panel = Panel.fit(_StrictMarkdown("the answer body"), title="Response")
    _safe_console_print(console, panel)
    assert "the answer body" in stream.getvalue()
