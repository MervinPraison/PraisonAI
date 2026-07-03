"""Regression tests for issue #2611 — coherent first-run.

Two guarantees a brand-new user depends on:

1. ``praisonai init`` prints a run command that actually exists.
2. Every CLI first-run entry point routes its implicit default model through
   ``resolve_default_model()`` instead of hard-coding ``gpt-4o-mini`` — so a
   user with only, say, ``ANTHROPIC_API_KEY`` set is defaulted to an
   appropriate model rather than an OpenAI one.

The grep-guard asserts no stray ``gpt-4o-mini`` literal remains in the
onboarding entry-point files; the shared fallback lives in one place
(``praisonai_code.llm.env.DEFAULT_FALLBACK_MODEL``) and is applied via the
resolver.
"""

import re
from pathlib import Path

import pytest

from praisonai_code.cli.configuration.model_resolver import (
    _fallback_model,
    resolve_default_model,
)
from praisonai_code.llm.env import DEFAULT_FALLBACK_MODEL


_CLI_ROOT = Path(__file__).resolve().parents[2] / "praisonai_code" / "cli"

# First-run / onboarding entry points that must never re-declare the terminal
# fallback literal — they route through resolve_default_model() or reference
# DEFAULT_FALLBACK_MODEL by name instead.
_ENTRY_POINT_FILES = (
    _CLI_ROOT / "app.py",
    _CLI_ROOT / "commands" / "init.py",
    _CLI_ROOT / "commands" / "chat.py",
    _CLI_ROOT / "commands" / "setup.py",
    _CLI_ROOT / "commands" / "test.py",
)

_LITERAL = re.compile(r"""["']gpt-4o-mini["']""")


@pytest.mark.parametrize("path", _ENTRY_POINT_FILES, ids=lambda p: p.name)
def test_no_hardcoded_default_model_literal(path):
    """No onboarding entry point may hard-code the ``gpt-4o-mini`` literal."""
    assert path.exists(), f"expected entry-point file missing: {path}"
    offenders = [
        f"{path.name}:{i}: {line.strip()}"
        for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
        if _LITERAL.search(line)
    ]
    assert not offenders, (
        "Hard-coded gpt-4o-mini literal(s) found; route through "
        "resolve_default_model()/DEFAULT_FALLBACK_MODEL instead:\n"
        + "\n".join(offenders)
    )


def test_fallback_model_matches_single_source_of_truth():
    """The resolver's terminal fallback comes from one shared constant."""
    assert _fallback_model() == DEFAULT_FALLBACK_MODEL


def test_resolver_prefers_explicit_model():
    assert resolve_default_model("my/model", persist=False) == "my/model"


def test_resolver_honours_provider_credentials(monkeypatch, tmp_path):
    """With only ANTHROPIC_API_KEY set, the default is an Anthropic model."""
    # Isolate state so no persisted recency short-circuits inference.
    monkeypatch.setattr(
        "praisonai_code.cli.configuration.model_resolver.get_recent_model",
        lambda: None,
    )
    for var in (
        "MODEL_NAME", "OPENAI_MODEL_NAME", "OPENAI_API_KEY", "GEMINI_API_KEY",
        "GOOGLE_API_KEY", "GROQ_API_KEY", "COHERE_API_KEY", "OLLAMA_HOST",
    ):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")

    resolved = resolve_default_model(None, persist=False, notify=False)

    assert resolved != "gpt-4o-mini"
    assert "claude" in resolved.lower() or resolved.startswith("anthropic/")


def test_init_prints_working_run_command():
    """The scaffolder hint must advertise a command that exists."""
    init_src = (_CLI_ROOT / "commands" / "init.py").read_text(encoding="utf-8")
    assert "praisonai run --agent assistant" in init_src
    assert "praisonai run --command review" in init_src
    # The previously-broken, non-existent invocation must be gone.
    assert "praisonai agent run assistant" not in init_src
    assert "praisonai command run review" not in init_src
