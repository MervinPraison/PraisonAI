"""
Unit tests for unicode_utils.py — ASCII-safe error message helpers.
"""

import pytest

import io

from praisonai_bot.gateway.unicode_utils import (
    safe_error_message,
    safe_log_message,
    extract_root_cause_from_error,
    safe_print,
)


class _Cp1252Stream:
    """Minimal text stream that rejects non-cp1252 chars, like a Windows console."""

    def __init__(self):
        self.buffer = []

    def write(self, text):
        text.encode("cp1252")  # raises UnicodeEncodeError on U+2551 etc.
        self.buffer.append(text)

    def getvalue(self):
        return "".join(self.buffer)


class TestSafeErrorMessage:
    """Tests for safe_error_message()."""

    def test_plain_ascii_unchanged(self):
        assert safe_error_message("hello world") == "hello world"

    def test_exception_converted(self):
        exc = ValueError("something went wrong")
        result = safe_error_message(exc)
        assert result == "something went wrong"

    def test_warning_symbol_replaced(self):
        # U+26A0 WARNING SIGN -> '!'
        result = safe_error_message("\u26a0 quota exceeded")
        assert result == "! quota exceeded"

    def test_smart_quotes_replaced(self):
        result = safe_error_message("\u201chello\u201d")
        assert result == '"hello"'

    def test_em_dash_replaced(self):
        result = safe_error_message("error\u2014details")
        assert result == "error--details"

    def test_box_drawing_playwright_hint_survives(self):
        # Playwright's "playwright install" banner uses box-drawing frame
        # characters (U+2551 etc.). They must not crash cp1252 output and the
        # actionable hint must remain readable (no '?' clutter over the frame).
        raw = "\u2551 Please run: playwright install \u2551"
        result = safe_error_message(raw)
        result.encode("ascii")  # must not raise
        assert "?" not in result
        assert "playwright install" in result

    def test_accented_chars_mapped(self):
        result = safe_error_message("caf\u00e9")   # café
        assert result == "cafe"

    def test_accented_uppercase_mapped(self):
        result = safe_error_message("\u00c9l\u00e8ve")  # Élève
        assert result == "Eleve"

    def test_nfkd_fallback_for_unlisted_accents(self):
        # 'ő' (U+0151, o with double acute) is not in _LATIN1_MAP but NFKD
        # decomposes it to 'o' + combining double acute -> base letter 'o'
        result = safe_error_message("\u0151")
        assert result == "o"

    def test_emoji_replaced_with_question_mark(self):
        result = safe_error_message("bot \U0001f916 ready")  # 🤖
        assert "?" in result

    def test_truncation(self):
        long_msg = "a" * 600
        result = safe_error_message(long_msg, max_len=100)
        assert len(result) == 100
        assert result.endswith("...")

    def test_empty_string_returns_default(self):
        result = safe_error_message("   ")
        assert result == "Error occurred"

    def test_none_type_exception(self):
        exc = Exception("")
        result = safe_error_message(exc)
        # str(Exception("")) is "" -> falls back to type name
        assert result  # not empty

    def test_output_is_ascii(self):
        """Output must be entirely 7-bit ASCII for all tested inputs."""
        inputs = [
            "\u26a0 API Error 429",
            "caf\u00e9 timeout",
            "Unicode \u03b1\u03b2\u03b3 chars",
            "\U0001f4a5 explosion",
        ]
        for text in inputs:
            result = safe_error_message(text)
            result.encode("ascii")  # raises UnicodeEncodeError if not ASCII


class TestSafeLogMessage:
    """Tests for safe_log_message()."""

    def test_plain_ascii_unchanged(self):
        assert safe_log_message("plain text") == "plain text"

    def test_unicode_preserved(self):
        # Regular Unicode (non-surrogate) must survive unchanged
        assert safe_log_message("caf\u00e9") == "caf\u00e9"

    def test_exception_stringified(self):
        exc = RuntimeError("oops")
        assert safe_log_message(exc) == "oops"

    def test_lone_surrogate_replaced(self):
        # Lone surrogates cannot be encoded in UTF-8
        text = "bad\ud800char"
        result = safe_log_message(text)
        assert "\ud800" not in result


class TestSafePrint:
    """Tests for safe_print()."""

    def test_plain_ascii_written_unchanged(self):
        out = io.StringIO()
        safe_print("hello world", file=out)
        assert out.getvalue() == "hello world\n"

    def test_utf8_stream_preserves_unicode(self):
        out = io.StringIO()  # StringIO accepts any unicode -> no sanitization
        safe_print("caf\u00e9", file=out)
        assert out.getvalue() == "caf\u00e9\n"

    def test_cp1252_stream_does_not_crash_on_box_char(self):
        # The core regression: U+2551 in a Playwright banner must not raise.
        stream = _Cp1252Stream()
        safe_print("\u2551 Please run: playwright install \u2551", file=stream)
        result = stream.getvalue()
        result.encode("cp1252")  # must not raise
        assert "playwright install" in result
        assert "\u2551" not in result

    def test_cp1252_multiline_banner_preserves_line_breaks(self):
        stream = _Cp1252Stream()
        banner = "updated.\n\u2551 run: playwright install \u2551\ndone"
        safe_print(banner, file=stream)
        result = stream.getvalue()
        assert result.count("\n") >= 2
        assert "playwright install" in result

    def test_sep_and_end_respected(self):
        out = io.StringIO()
        safe_print("a", "b", sep="-", end="!", file=out)
        assert out.getvalue() == "a-b!"


class TestExtractRootCause:
    """Tests for extract_root_cause_from_error()."""

    def test_openai_error_code_pattern(self):
        msg = "Error code: 429 - You exceeded your current quota"
        result = extract_root_cause_from_error(msg)
        assert "429" in result
        assert "exceeded" in result.lower()

    def test_quota_keyword(self):
        result = extract_root_cause_from_error("insufficient_quota for this model")
        assert "quota" in result.lower()

    def test_rate_limit_keyword(self):
        result = extract_root_cause_from_error("Rate limit exceeded, slow down")
        assert "rate limit" in result.lower() or "Rate limit" in result

    def test_authentication_keyword(self):
        result = extract_root_cause_from_error("Authentication failed: bad key")
        assert "auth" in result.lower()

    def test_timeout_keyword(self):
        result = extract_root_cause_from_error("connection timeout reached")
        assert "timeout" in result.lower()

    def test_unrecognised_returns_original(self):
        original = "some random error text"
        assert extract_root_cause_from_error(original) == original

    def test_result_goes_through_safe_error_message(self):
        """Callers always pass result to safe_error_message; ensure chain is safe."""
        raw = "Error code: 429 - \u26a0 quota exceeded"
        root = extract_root_cause_from_error(raw)
        safe = safe_error_message(root)
        safe.encode("ascii")  # must not raise
