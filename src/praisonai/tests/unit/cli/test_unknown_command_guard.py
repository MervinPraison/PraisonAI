"""Regression tests for the unknown-command guard (issue #2781).

A bare verb like `praisonai show` must NOT silently become a paid one-shot
LLM prompt. It should fail fast with a helpful hint instead.
"""

from __future__ import annotations

import pytest

from praisonai.cli.legacy.dispatch.argparse_builder import (
    RESERVED_UNKNOWN_VERBS,
    classify_unknown_command,
)

SPECIAL_COMMANDS = [
    "chat", "code", "memory", "version", "config", "paths", "run", "docs",
]


def test_reserved_show_returns_hint():
    hint = classify_unknown_command("show", SPECIAL_COMMANDS)
    assert hint is not None
    assert "Unknown command" in hint
    assert "paths" in hint
    assert "memory show" in hint


def test_reserved_show_case_insensitive():
    assert classify_unknown_command("SHOW", SPECIAL_COMMANDS) is not None


def test_typo_of_known_command_returns_suggestion():
    hint = classify_unknown_command("memoyr", SPECIAL_COMMANDS)
    assert hint is not None
    assert "Did you mean" in hint
    assert "memory" in hint


def test_multiword_prompt_is_not_guarded():
    # Genuine natural-language prompts must still work as direct prompts.
    assert classify_unknown_command("write a poem", SPECIAL_COMMANDS) is None


def test_unrelated_single_word_is_not_guarded():
    # A lone word that isn't reserved and doesn't fuzzy-match stays a prompt.
    assert classify_unknown_command("hello", SPECIAL_COMMANDS) is None


def test_empty_command_returns_none():
    assert classify_unknown_command("", SPECIAL_COMMANDS) is None
    assert classify_unknown_command(None, SPECIAL_COMMANDS) is None


def test_show_is_reserved():
    assert "show" in RESERVED_UNKNOWN_VERBS
