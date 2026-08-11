"""Regression tests for issue #3655.

``praisonai models list`` must not crash on Windows consoles using the default
cp1252 encoding. The original failure was a ``UnicodeEncodeError`` raised while
Rich rendered emoji characters (U+1F527 wrench, U+1F441 eye, U+1F9E0 brain)
embedded in the Capabilities column, and ✅/❌ in ``describe``/``validate``.

These tests assert that capability strings fall back to ASCII labels when
stdout cannot encode emoji, while preserving emoji on UTF-8 terminals.
"""

from unittest.mock import patch

from praisonai_code.cli.commands.models import _capabilities_label
from praisonai_code.cli.output import console as console_mod


SAMPLE_MODEL = {
    "id": "gpt-4o",
    "provider": "openai",
    "supports_tools": True,
    "supports_vision": True,
    "supports_reasoning": False,
}


def _cp1252_encodable(text: str) -> bool:
    try:
        text.encode("cp1252")
        return True
    except UnicodeEncodeError:
        return False


def test_capabilities_label_ascii_fallback():
    label = _capabilities_label(SAMPLE_MODEL, use_emoji=False)
    assert label == "tools vision"
    assert _cp1252_encodable(label)


def test_capabilities_label_emoji_when_supported():
    label = _capabilities_label(SAMPLE_MODEL, use_emoji=True)
    assert "🔧" in label
    assert "👁️" in label


def test_capabilities_label_empty():
    assert _capabilities_label({}, use_emoji=True) == "-"
    assert _capabilities_label({}, use_emoji=False) == "-"


class _FakeStdout:
    def __init__(self, encoding):
        self.encoding = encoding


def test_stdout_supports_unicode_cp1252_false():
    with patch.object(console_mod.sys, "stdout", _FakeStdout("cp1252")):
        assert console_mod.stdout_supports_unicode() is False


def test_stdout_supports_unicode_utf8_true():
    with patch.object(console_mod.sys, "stdout", _FakeStdout("utf-8")):
        assert console_mod.stdout_supports_unicode() is True


def test_capabilities_label_cp1252_end_to_end():
    """With cp1252 stdout the produced label must encode cleanly."""
    with patch.object(console_mod.sys, "stdout", _FakeStdout("cp1252")):
        use_emoji = console_mod.stdout_supports_unicode()
    label = _capabilities_label(SAMPLE_MODEL, use_emoji=use_emoji)
    assert _cp1252_encodable(label)
