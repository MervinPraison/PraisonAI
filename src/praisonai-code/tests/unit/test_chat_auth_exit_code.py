"""Regression tests for issue #2562.

``praisonai chat`` must return a non-zero exit code when the LLM call fails
with an authentication error (e.g. an invalid ``OPENAI_API_KEY``) instead of
silently exiting 0. These tests exercise the failure-detection plumbing in
``AsyncTUI`` without making any real network calls.
"""

import logging

from praisonai_code.cli.interactive.async_tui import (
    AsyncTUI,
    AsyncTUIConfig,
    _LogCapture,
    _detect_auth_error,
)


def _make_tui():
    return AsyncTUI(config=AsyncTUIConfig(show_logo=False, show_status_bar=False))


def test_detect_auth_error_matches_common_signatures():
    assert _detect_auth_error("Incorrect API key provided") is not None
    assert _detect_auth_error("HTTP 401 Unauthorized") is not None
    assert _detect_auth_error("Authentication failed for openai") is not None
    assert _detect_auth_error("invalid_api_key") is not None


def test_detect_auth_error_ignores_success_text():
    assert _detect_auth_error("Here is your answer: 4") is None
    assert _detect_auth_error("") is None
    assert _detect_auth_error(None) is None


def test_log_capture_finds_auth_error():
    capture = _LogCapture(level=logging.WARNING)
    record = logging.LogRecord(
        name="chat_mixin", level=logging.WARNING, pathname=__file__,
        lineno=1485, msg="Authentication failed for openai", args=(), exc_info=None,
    )
    capture.emit(record)
    assert capture.find_auth_error() is not None


def test_execution_failed_flag_set_on_exception(monkeypatch):
    tui = _make_tui()

    class _BoomAgent:
        name = "ChatAgent"
        tools = []

        def start(self, prompt):
            raise RuntimeError("Error code: 401 - invalid_api_key")

    monkeypatch.setattr(tui, "_get_agent", lambda: _BoomAgent())

    result = tui.run_single("Hello")

    assert tui.execution_failed is True
    assert result is not None and result.startswith("Error")


def test_execution_failed_flag_set_on_logged_auth_error(monkeypatch):
    """agent.start() logs an auth error but returns None (silent failure)."""
    tui = _make_tui()

    class _SilentAuthAgent:
        name = "ChatAgent"
        tools = []

        def start(self, prompt):
            logging.getLogger("chat_mixin").warning(
                "Authentication failed for openai"
            )
            return None

    monkeypatch.setattr(tui, "_get_agent", lambda: _SilentAuthAgent())

    tui.run_single("Hello")

    assert tui.execution_failed is True


def test_execution_not_failed_on_success(monkeypatch):
    tui = _make_tui()

    class _OkAgent:
        name = "ChatAgent"
        tools = []

        def start(self, prompt):
            return "The answer is 4"

    monkeypatch.setattr(tui, "_get_agent", lambda: _OkAgent())

    result = tui.run_single("What is 2+2?")

    assert tui.execution_failed is False
    assert result == "The answer is 4"
