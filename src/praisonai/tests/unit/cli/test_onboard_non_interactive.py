"""Unit tests for non-interactive mode in ``praisonai onboard``.

Verifies that when ``PRAISONAI_NO_PROMPT=1`` is set (or ``--yes``/``-y``
is passed, which sets the same env var), the wizard never blocks on any
blocking prompt — every ``Prompt.ask`` / ``Confirm.ask`` / ``input`` /
``getpass.getpass`` call short-circuits to its declared default.

Regression protection: if a new blocking prompt is added later, this
suite fails because unpatched blocking I/O would hang and the test
runner's timeout would fire.
"""

import os
import sys

import pytest


@pytest.fixture(autouse=True)
def _clear_no_prompt_env():
    """Ensure PRAISONAI_NO_PROMPT is scoped to each test."""
    original = os.environ.pop("PRAISONAI_NO_PROMPT", None)
    yield
    if original is None:
        os.environ.pop("PRAISONAI_NO_PROMPT", None)
    else:
        os.environ["PRAISONAI_NO_PROMPT"] = original


def _import_onboard():
    """Lazy import so the test suite doesn't pay onboard's import cost
    when it's collecting unrelated tests."""
    from praisonai.cli.features import onboard
    return onboard


def test_is_non_interactive_false_by_default():
    onboard = _import_onboard()
    # stdin in pytest is typically not a TTY — acknowledge that.
    # When NO_PROMPT is unset, detection falls back to stdin.isatty.
    # Most CI/pytest runs are not TTYs, so this returns True.
    # We only assert the env-var branch here.
    os.environ.pop("PRAISONAI_NO_PROMPT", None)
    # If stdin happens to be a TTY (rare in CI), we can't assert anything
    # stronger — the function should return False.
    try:
        is_tty = sys.stdin.isatty()
    except (AttributeError, ValueError):
        is_tty = False
    expected = not is_tty
    assert onboard._is_non_interactive() is expected


def test_is_non_interactive_true_when_env_set():
    onboard = _import_onboard()
    import io
    saved = sys.stdin
    try:
        sys.stdin = io.StringIO("")
        sys.stdin.isatty = lambda: True  # isolate env-var branch
        for val in ("1", "true", "yes", "on", "TRUE", "Yes"):
            os.environ["PRAISONAI_NO_PROMPT"] = val
            assert onboard._is_non_interactive() is True, f"failed for value {val!r}"
    finally:
        sys.stdin = saved


def test_is_non_interactive_false_when_env_explicitly_off():
    onboard = _import_onboard()
    # Empty / zero / "false" / "no" must NOT trigger non-interactive mode
    # by themselves. (Whether it's on because stdin isn't a tty is a
    # separate concern and is tested elsewhere.)
    for val in ("0", "false", "no", "off", ""):
        os.environ["PRAISONAI_NO_PROMPT"] = val
        # In pytest stdin is likely not a tty, so this may still be True
        # via the tty-fallback. We only test that the env branch doesn't
        # force it on for these values.
        #
        # To isolate the env branch, monkey-patch isatty temporarily.
        import io
        saved = sys.stdin
        try:
            sys.stdin = io.StringIO("")
            sys.stdin.isatty = lambda: True  # pretend we have a tty
            assert onboard._is_non_interactive() is False, f"failed for value {val!r}"
        finally:
            sys.stdin = saved


def test_prompt_ask_returns_default_in_non_interactive():
    onboard = _import_onboard()
    os.environ["PRAISONAI_NO_PROMPT"] = "1"

    class _FakePrompt:
        @staticmethod
        def ask(*args, **kwargs):
            raise AssertionError(
                "Prompt.ask must not be called in non-interactive mode"
            )

    # Non-interactive + default provided → returns the default
    assert onboard._prompt_ask(_FakePrompt, "irrelevant", default="telegram") == "telegram"
    # No default → returns empty string
    assert onboard._prompt_ask(_FakePrompt, "irrelevant") == ""


def test_confirm_ask_returns_default_in_non_interactive():
    onboard = _import_onboard()
    os.environ["PRAISONAI_NO_PROMPT"] = "1"

    class _FakeConfirm:
        @staticmethod
        def ask(*args, **kwargs):
            raise AssertionError(
                "Confirm.ask must not be called in non-interactive mode"
            )

    assert onboard._confirm_ask(_FakeConfirm, "irrelevant", default=False) is False
    assert onboard._confirm_ask(_FakeConfirm, "irrelevant", default=True) is True
    # No default → False
    assert onboard._confirm_ask(_FakeConfirm, "irrelevant") is False


def test_plain_input_returns_default_in_non_interactive(monkeypatch):
    onboard = _import_onboard()
    os.environ["PRAISONAI_NO_PROMPT"] = "1"

    def _boom(*args, **kwargs):
        raise AssertionError("input() must not be called in non-interactive mode")

    monkeypatch.setattr("builtins.input", _boom)
    assert onboard._plain_input("irrelevant: ", default="telegram") == "telegram"
    assert onboard._plain_input("irrelevant: ") == ""


def test_plain_getpass_returns_empty_in_non_interactive(monkeypatch):
    onboard = _import_onboard()
    os.environ["PRAISONAI_NO_PROMPT"] = "1"

    def _boom(*args, **kwargs):
        raise AssertionError(
            "getpass.getpass() must not be called in non-interactive mode"
        )

    monkeypatch.setattr("getpass.getpass", _boom)
    assert onboard._plain_getpass("irrelevant: ") == ""


def test_wizard_run_does_not_block_in_non_interactive(monkeypatch, tmp_path):
    """End-to-end: ``OnboardWizard.run()`` completes in non-interactive mode
    without ever invoking a blocking prompt.

    Regression canary — if any future Prompt.ask / Confirm.ask slips in
    that bypasses the wrapper, this test will raise via the fake classes.
    """
    onboard = _import_onboard()
    os.environ["PRAISONAI_NO_PROMPT"] = "1"

    # Redirect the config file into tmp_path so we don't touch the real home.
    monkeypatch.setenv("HOME", str(tmp_path))
    # Ensure daemon installation is skipped — we don't want this test
    # trying to launchctl/systemctl anything.
    monkeypatch.setattr(
        "praisonai.cli.features.onboard.OnboardWizard._install_daemon_with_feedback",
        lambda self, print_fn, config_path: False,
    )
    # Skip the live telegram probe — we have no real token.
    async def _fake_probe(self, platform):
        class _R:
            ok = False
            error = "skipped in test"
            elapsed_ms = 0
            bot_username = "n/a"
        return _R()
    monkeypatch.setattr(
        "praisonai.cli.features.onboard.OnboardWizard._probe", _fake_probe
    )

    # Install tripwires on any blocking prompt path.
    import rich.prompt

    def _boom(*args, **kwargs):
        raise AssertionError(
            "blocking prompt called during non-interactive onboard run"
        )
    monkeypatch.setattr(rich.prompt.Prompt, "ask", _boom)
    monkeypatch.setattr(rich.prompt.Confirm, "ask", _boom)
    monkeypatch.setattr("builtins.input", _boom)
    monkeypatch.setattr("getpass.getpass", _boom)

    wizard = onboard.OnboardWizard()
    # Must complete without raising.
    wizard.run()
