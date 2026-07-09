"""Regression tests for the standalone `run` wrapper gate (issue #2839).

Structured output modes (actions/json/stream/stream-json) run in-process via the
Agent path and never need the wrapper. Human-readable text modes
(plain/verbose/silent/default) delegate to the wrapper's `handle_direct_prompt`;
on a standalone install (no `praisonai` wrapper) they gate via
`_require_wrapper_for_default_run` with an install hint. This keeps the C7 hot
path free of the heavy Agent import for default text runs and matches the
`smoke` job contract.

The valuable fix from #2839 preserved here is the corrected error hint, which
now cites `praisonai-code run --output actions` instead of `praisonai`.
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
def test_text_modes_need_wrapper(mode):
    """Human-readable text modes always route to the wrapper text path."""
    assert (
        run_cmd._direct_prompt_needs_wrapper(
            "hi", agent=None, command=None, output_mode=mode
        )
        is True
    )


@pytest.mark.parametrize("mode", ["actions", "json", "stream", "stream-json"])
def test_structured_modes_never_need_wrapper(mode):
    assert (
        run_cmd._direct_prompt_needs_wrapper(
            "hi", agent=None, command=None, output_mode=mode
        )
        is False
    )


@pytest.mark.parametrize("kwargs", [
    {"agent": "reviewer", "command": None},
    {"agent": None, "command": "deploy"},
])
def test_agent_or_command_never_need_wrapper(kwargs):
    assert (
        run_cmd._direct_prompt_needs_wrapper(
            "hi", output_mode=None, **kwargs
        )
        is False
    )


def test_no_target_does_not_need_wrapper():
    assert (
        run_cmd._direct_prompt_needs_wrapper(
            None, agent=None, command=None, output_mode=None
        )
        is False
    )


def test_require_wrapper_noop_when_wrapper_installed(with_wrapper):
    """With the wrapper installed, the gate passes through (delegation happens)."""
    run_cmd._require_wrapper_for_default_run(
        "hi", agent=None, command=None, output_mode="plain"
    )


def test_require_wrapper_noop_for_structured_mode(no_wrapper):
    """Structured modes run in-process, so the gate never trips for them."""
    run_cmd._require_wrapper_for_default_run(
        "hi", agent=None, command=None, output_mode="actions"
    )


@pytest.mark.parametrize("mode", [None, "silent", "plain", "verbose"])
def test_require_wrapper_error_references_praisonai_code(monkeypatch, mode):
    """Standalone text runs gate with a hint that cites praisonai-code."""
    monkeypatch.setattr(
        "praisonai_code._wrapper_bridge.wrapper_available", lambda: False
    )

    messages = []

    class _Output:
        def print_error(self, msg):
            messages.append(msg)

    monkeypatch.setattr(run_cmd, "get_output_controller", lambda: _Output())

    import typer

    with pytest.raises(typer.Exit):
        run_cmd._require_wrapper_for_default_run(
            "hi", agent=None, command=None, output_mode=mode
        )

    assert messages
    assert 'praisonai-code run --output actions "your prompt"' in messages[0]
    assert "praisonai run --output actions" not in messages[0]
