"""Regression tests for issue #2699.

``praisonai-code --help`` must not crash on Windows consoles using the default
cp1252 encoding. The original failure was a ``UnicodeEncodeError`` raised while
Rich rendered emoji characters embedded in command help strings (for example
U+1F31F in the ``dashboard`` entry of ``_LAZY_COMMANDS``).

These tests assert that the top-level help output contains no emoji-range
characters so the command list renders cleanly on legacy Windows terminals.
"""

from typer.testing import CliRunner

from praisonai_code.cli.app import app


def _emoji_codepoints(text: str) -> list:
    return sorted({hex(ord(c)) for c in text if ord(c) >= 0x1F000})


# Rich renders panels/tables using Unicode box-drawing characters. These are NOT
# the cause of the #2699 crash: Rich detects legacy (cp1252) Windows consoles and
# automatically substitutes ASCII box characters at render time, so they never
# reach the encoder. The CliRunner captures the rich box output regardless of the
# host terminal, so we exclude the box-drawing block (U+2500-U+257F) when checking
# for characters that would genuinely break a cp1252 console.
_BOX_DRAWING_RANGE = range(0x2500, 0x2580)


def _cp1252_unsafe_chars(text: str) -> list:
    """Return codepoints that a cp1252 (legacy Windows) console cannot encode.

    Box-drawing characters that Rich downgrades automatically are ignored.
    """
    unsafe = []
    for c in text:
        if ord(c) in _BOX_DRAWING_RANGE:
            continue
        try:
            c.encode("cp1252")
        except UnicodeEncodeError:
            unsafe.append(hex(ord(c)))
    return sorted(set(unsafe))


def test_main_help_exits_zero():
    result = CliRunner().invoke(app, ["--help"])
    assert result.exit_code == 0


def test_main_help_has_no_emoji():
    result = CliRunner().invoke(app, ["--help"])
    assert _emoji_codepoints(result.output) == []


def test_main_help_is_cp1252_encodable():
    result = CliRunner().invoke(app, ["--help"])
    assert _cp1252_unsafe_chars(result.output) == [], (
        "praisonai-code --help emitted characters that crash cp1252 consoles"
    )


def test_lazy_commands_help_strings_are_ascii():
    from praisonai_code.cli.app import _LAZY_COMMANDS

    for name, entry in _LAZY_COMMANDS.items():
        help_text = entry[2]
        assert all(ord(c) < 128 for c in help_text), (
            f"non-ASCII in help for command {name!r}: {help_text!r}"
        )
