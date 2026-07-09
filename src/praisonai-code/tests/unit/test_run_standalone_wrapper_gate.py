"""Regression tests for the standalone `run` wrapper gate (issue #2839).

On a standalone install (no `praisonai` wrapper) human-readable output modes
(plain/verbose/silent/default) for a direct text prompt must NOT be blocked by
`_require_wrapper_for_default_run`; they route through the in-process Agent
path instead. Structured modes (actions/json/stream) never needed the wrapper.
When the wrapper IS installed, text modes still prefer its `handle_direct_prompt`.
"""

import pytest

from praisonai_code.cli.commands import run as run_cmd


@pytest.fixture
def no_wrapper(monkeypatch):
    monkeypatch.setattr(
        "praisonai_code._wrapper_bridge.wrapper_available", lambda: False
    )


@pytest.fixture
def with_wrapper(monkeypatch):
    monkeypatch.setattr(
        "praisonai_code._wrapper_bridge.wrapper_available", lambda: True
    )


@pytest.mark.parametrize("mode", [None, "silent", "plain", "verbose"])
def test_text_modes_no_wrapper_do_not_need_wrapper(no_wrapper, mode):
    assert (
        run_cmd._direct_prompt_needs_wrapper(
            "hi", agent=None, command=None, output_mode=mode
        )
        is False
    )


@pytest.mark.parametrize("mode", [None, "silent", "plain", "verbose"])
def test_text_modes_with_wrapper_prefer_wrapper(with_wrapper, mode):
    assert (
        run_cmd._direct_prompt_needs_wrapper(
            "hi", agent=None, command=None, output_mode=mode
        )
        is True
    )


@pytest.mark.parametrize("mode", ["actions", "json", "stream", "stream-json"])
def test_structured_modes_never_need_wrapper(with_wrapper, mode):
    assert (
        run_cmd._direct_prompt_needs_wrapper(
            "hi", agent=None, command=None, output_mode=mode
        )
        is False
    )


def test_require_wrapper_noop_on_standalone_text_mode(no_wrapper):
    run_cmd._require_wrapper_for_default_run(
        "hi", agent=None, command=None, output_mode="plain"
    )


def test_require_wrapper_error_references_praisonai_code(monkeypatch):
    """When the gate does trip, the standalone hint must cite praisonai-code."""
    monkeypatch.setattr(
        "praisonai_code._wrapper_bridge.wrapper_available", lambda: False
    )
    # Force the "needs wrapper" branch so the error path is exercised.
    monkeypatch.setattr(
        run_cmd, "_direct_prompt_needs_wrapper", lambda *a, **k: True
    )

    messages = []

    class _Output:
        def print_error(self, msg):
            messages.append(msg)

    monkeypatch.setattr(run_cmd, "get_output_controller", lambda: _Output())

    import typer

    with pytest.raises(typer.Exit):
        run_cmd._require_wrapper_for_default_run(
            "hi", agent=None, command=None, output_mode="plain"
        )

    assert messages
    assert 'praisonai-code run --output actions "your prompt"' in messages[0]
