"""Parity tests across the interactive REPL surfaces (issue #3744).

Covers four cross-surface consistency defects:

1. The async TUI must actually expand advertised ``@filename`` mentions on
   submit (not just autocomplete them).
2. ``/stats`` must be available on every REPL surface, not only the legacy one.
3. The legacy REPL (what ``praisonai code`` runs) must offer ``/export``.
4. There must be a single ``create_default_registry`` symbol — the legacy
   ``slash_commands`` registry factory is renamed to avoid the duplicate.
"""

import os
import tempfile

import pytest


# ---------------------------------------------------------------------------
# Defect 1: async TUI expands @file mentions on submit
# ---------------------------------------------------------------------------

def test_async_tui_expands_at_mentions():
    """``@file`` mentions must be expanded exactly once on the execution path.

    The submit flow queues the *raw* prompt; expansion happens canonically in
    ``_execute_in_background`` via ``_process_file_mentions``. This asserts both
    that the advertised expansion runs and that it runs only once (a second pass
    would re-interpret ``@tokens`` inside attached file contents).
    """
    from praisonai.cli.interactive.async_tui import AsyncTUI

    tui = AsyncTUI()

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".txt", delete=False
    ) as f:
        f.write("SENTINEL_FILE_BODY")
        temp_path = f.name

    try:
        tui.config.workspace = os.path.dirname(temp_path)
        filename = os.path.basename(temp_path)

        calls = {"count": 0}
        real_process = tui._process_file_mentions

        def _counting_process(prompt):
            calls["count"] += 1
            return real_process(prompt)

        tui._process_file_mentions = _counting_process

        # Capture the fully-processed prompt handed to the LLM without running
        # a real agent/thread.
        captured = {}

        def _fake_execute(prompt, read_only=False):
            captured["prompt"] = prompt
            return "ok"

        tui._execute_prompt = _fake_execute

        # Drive the real background execution path synchronously.
        import threading

        real_thread = threading.Thread

        class _InlineThread:
            def __init__(self, target=None, daemon=None):
                self._target = target

            def start(self):
                if self._target:
                    self._target()

            def join(self):
                pass

        threading.Thread = _InlineThread
        try:
            tui._execute_in_background(f"Check @{filename}")
        finally:
            threading.Thread = real_thread

        # Expansion happened, and exactly once.
        assert "SENTINEL_FILE_BODY" in captured["prompt"]
        assert calls["count"] == 1
    finally:
        os.unlink(temp_path)


# ---------------------------------------------------------------------------
# Defect 2: /stats available on all REPL surfaces
# ---------------------------------------------------------------------------

def test_stats_available_all_repls():
    """Every interactive surface should expose a ``/stats`` command."""
    # Async TUI: /stats is a first-class command and a help/builtin entry.
    from praisonai.cli.interactive.async_tui import AsyncTUI

    tui = AsyncTUI()
    tui._total_tokens = 123
    tui._total_cost = 0.0042
    assert tui._handle_command("/stats") is True
    assert "123" in tui.messages[0].content
    assert "stats" in tui._BUILTIN_COMMANDS

    # Legacy REPL: dedicated stats renderer exists.
    il = pytest.importorskip("praisonai.cli.legacy.interactive_legacy")
    assert hasattr(il, "_handle_stats_command")


# ---------------------------------------------------------------------------
# Defect 3: legacy REPL /export
# ---------------------------------------------------------------------------

def test_legacy_export(tmp_path):
    """The legacy REPL must be able to export the conversation to a file."""
    il = pytest.importorskip("praisonai.cli.legacy.interactive_legacy")
    assert hasattr(il, "_handle_export_command")

    class _Console:
        def print(self, *args, **kwargs):
            pass

    session_state = {
        "unified_session": None,
        "conversation_history": [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi there"},
        ],
    }

    out_file = tmp_path / "transcript.md"
    il._handle_export_command(None, _Console(), str(out_file), session_state)

    assert out_file.exists()
    body = out_file.read_text()
    assert "hello" in body
    assert "hi there" in body


# ---------------------------------------------------------------------------
# Defect 4: single command registry (no duplicate create_default_registry)
# ---------------------------------------------------------------------------

def test_single_command_registry():
    """The legacy slash-command module must not shadow the canonical factory."""
    from praisonai.cli.features import slash_commands

    # The duplicate factory is gone; the legacy one is renamed distinctly.
    assert not hasattr(slash_commands, "create_default_registry")
    assert hasattr(slash_commands, "create_slash_command_registry")

    # The canonical registry factory still lives in command_registry.
    from praisonai_code.cli.interactive import command_registry

    assert hasattr(command_registry, "create_default_registry")

    # The legacy handler keeps working off the renamed factory.
    handler = slash_commands.SlashCommandHandler(discover_custom=False)
    assert handler.registry.get("help") is not None
