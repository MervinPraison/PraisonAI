"""
Provider-aware default model resolution with last-used recency.

Resolves a sensible default model for zero-config first runs in this
precedence:

1. Explicit value (``--model`` / config / YAML) — handled by the caller.
2. Most-recently-used model, persisted under ``~/.praison/state/model.json``.
3. Best available model inferred from which provider credentials are present
   (delegated to :func:`default_model_for_available_provider`).

This is a wrapper/first-run concern: recency state, credential scanning and the
one-line CLI notice live here, while core only owns a small provider-aware
helper that maps present credentials to a default.
"""

import json
import os
from pathlib import Path
from typing import Optional

from .paths import get_user_config_dir


def _state_dir() -> Path:
    """Return the user state directory (``~/.praison/state``)."""
    return get_user_config_dir() / "state"


def _model_state_path() -> Path:
    """Return the recency file path (``~/.praison/state/model.json``)."""
    return _state_dir() / "model.json"


def get_recent_model() -> Optional[str]:
    """Return the most-recently-used model, or ``None`` if not recorded."""
    try:
        path = _model_state_path()
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        model = data.get("model")
        return model if isinstance(model, str) and model else None
    except Exception:
        # Never let a corrupt/unreadable state file break model resolution.
        return None


def set_recent_model(model: Optional[str]) -> bool:
    """Persist ``model`` as the most-recently-used model.

    Returns ``True`` on success, ``False`` if persistence failed (e.g. a
    read-only home directory). Failure is non-fatal — the model still works
    for the current run, it just won't be remembered.
    """
    if not model:
        return False
    try:
        state_dir = _state_dir()
        state_dir.mkdir(parents=True, exist_ok=True)
        _model_state_path().write_text(
            json.dumps({"model": model}), encoding="utf-8"
        )
        return True
    except Exception:
        return False


def _provider_for_model(model: str) -> Optional[str]:
    """Best-effort map a model id to the credential env var that explains it."""
    m = model.lower()
    if m.startswith("anthropic/") or m.startswith("claude"):
        return "ANTHROPIC_API_KEY"
    if m.startswith("gemini/") or m.startswith("gemini"):
        return "GEMINI_API_KEY"
    if m.startswith("google/"):
        return "GOOGLE_API_KEY"
    if m.startswith("groq/"):
        return "GROQ_API_KEY"
    if m.startswith("cohere/"):
        return "COHERE_API_KEY"
    if m.startswith("ollama/"):
        return "OLLAMA_HOST"
    if (
        m.startswith("gpt")
        or m.startswith("o1")
        or m.startswith("o3")
        or m.startswith("o4")
        or m.startswith("openai/")
    ):
        return "OPENAI_API_KEY"
    return None


def resolve_default_model(
    explicit: Optional[str] = None,
    *,
    persist: bool = True,
    notify: bool = True,
) -> str:
    """Resolve the default model for a zero-config run.

    Precedence: ``explicit`` > recent (persisted) > ``MODEL_NAME`` /
    ``OPENAI_MODEL_NAME`` > provider-aware best > ``gpt-4o-mini``.

    Only *user-chosen* models (``explicit`` and the env overrides) are
    persisted as the recent model. Provider-*inferred* defaults and the
    ``gpt-4o-mini`` fallback are intentionally **not** persisted: persisting
    them would let a stale inferred default short-circuit credential-based
    inference on a later run after the user's available providers have changed.

    Args:
        explicit: An explicitly configured model (``--model``/config/YAML).
            When given it wins and is persisted as the recent model.
        persist: Whether to remember user-chosen models for next time.
        notify: Whether to emit a one-line transparency notice the first time a
            provider-aware default is inferred (no explicit, no recent model).

    Returns:
        The resolved model id.
    """
    if explicit:
        if persist:
            set_recent_model(explicit)
        return explicit

    recent = get_recent_model()
    if recent:
        return recent

    # Honour OPENAI_MODEL_NAME / MODEL_NAME for backward compatibility before
    # falling back to credential-based inference.
    env_model = os.environ.get("MODEL_NAME") or os.environ.get("OPENAI_MODEL_NAME")
    if env_model:
        if persist:
            set_recent_model(env_model)
        return env_model

    try:
        from praisonai_code.llm.env import default_model_for_available_provider
        model = default_model_for_available_provider()
    except Exception:
        model = "gpt-4o-mini"

    if notify:
        provider = _provider_for_model(model)
        if provider and os.environ.get(provider):
            try:
                import typer
                typer.echo(
                    f"No model set; using {model} because {provider} is present."
                )
            except Exception:
                pass

    # NOTE: provider-inferred defaults and the gpt-4o-mini fallback are
    # deliberately NOT persisted. Persisting them would let a stale inferred
    # default win over fresh credential-based inference on a later run when the
    # user's available providers have changed, re-introducing the very
    # zero-config failure this resolver exists to prevent.
    return model
