"""Tests for ServeHandler._parse_args option handling (issue #6714)."""

import pytest

from praisonai.cli.features.serve import ServeArgumentError, ServeHandler

SPEC = {
    "host": {"default": "127.0.0.1"},
    "port": {"default": 8765, "type": "int"},
    "reload": {"flag": True, "default": False},
}


def test_space_separated_values():
    parsed = ServeHandler()._parse_args(["--host", "0.0.0.0", "--port", "9000", "--reload"], SPEC)
    assert parsed == {"host": "0.0.0.0", "port": 9000, "reload": True}


def test_equals_form_values():
    parsed = ServeHandler()._parse_args(["--port=9000", "--host=0.0.0.0"], SPEC)
    assert parsed["port"] == 9000
    assert parsed["host"] == "0.0.0.0"


def test_defaults_when_no_args():
    assert ServeHandler()._parse_args([], SPEC) == {"host": "127.0.0.1", "port": 8765, "reload": False}


@pytest.mark.parametrize(
    "args, message",
    [
        (["--prot", "9000"], "unrecognized option: --prot"),
        (["--port", "abc"], "invalid int value: 'abc'"),
        (["--port=abc"], "invalid int value: 'abc'"),
        (["--port"], "--port expects a value"),
        (["--reload=yes"], "--reload does not take a value"),
    ],
)
def test_invalid_options_raise(args, message):
    with pytest.raises(ServeArgumentError, match=message):
        ServeHandler()._parse_args(args, SPEC)


def test_handle_reports_bad_option_instead_of_starting(capsys):
    code = ServeHandler().handle(["agents", "--port", "abc"])
    assert code == ServeHandler.EXIT_VALIDATION_ERROR
    captured = capsys.readouterr()
    assert "invalid int value" in captured.out + captured.err
