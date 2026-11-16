"""
Provider-aware default model resolution with last-used recency.

Resolves a sensible default model for zero-config first runs in this
precedence:

1. Explicit value (``--model`` / config / YAML) — handled by the caller.
2. Most-recently-used model, persisted under the canonical state home
   (``<state>/state/model.json``; e.g. ``~/.praisonai/state/model.json`` or
   ``$XDG_STATE_HOME/praisonai/state/model.json``).
3. Best available model inferred from which provider credentials are present
   (delegated to :func:`default_model_for_available_provider`).

This is a wrapper/first-run concern: recency state, credential scanning and the
one-line CLI notice live here, while core only owns a small provider-aware
helper that maps present credentials to a default.
"""

import json
import os
from pathlib import Path
from typing import Optional, Tuple

from .paths import get_state_dir


def _fallback_model() -> str:
    """Return the terminal fallback model from its single source of truth.

    Kept out of this module so no CLI entry point ever re-declares the literal;
    they route through :func:`resolve_default_model` instead.
    """
    from praisonai_code.llm.env import DEFAULT_FALLBACK_MODEL
    return DEFAULT_FALLBACK_MODEL


def _state_dir() -> Path:
    """Return the user state directory (``<state>/state``).

    Anchored on the canonical state home (``get_state_dir``) so recency shares
    one location with the rest of the SDK — ending the historical
    ``~/.praison`` vs ``~/.praisonai`` split — and honours ``XDG_STATE_HOME``.
    """
    return get_state_dir() / "state"


def _model_state_path() -> Path:
    """Return the recency file path (``<state>/state/model.json``)."""
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
    """Best-effort map a model id to the credential env var that explains it.

    Resolves against the canonical ``PROVIDER_ENV_CATALOGUE`` so every
    catalogued provider (OpenRouter, Mistral, DeepSeek, xAI, …) is covered by
    one source of truth rather than a hand-maintained if-ladder that drifts.
    When a provider declares multiple credential env-vars, prefer whichever the
    user actually set so the notice names the live key. Falls back to the
    historical eight-provider ladder only when the catalogue import is
    unavailable (offline/degraded), exactly as the credential path does.
    """
    try:
        from praisonai_code.llm.catalogue import (
            provider_for_model,
            env_vars_for_provider,
        )

        provider = provider_for_model(model)
        if provider:
            vars_ = env_vars_for_provider(provider)
            if vars_:
                return next(
                    (var for var in vars_ if os.environ.get(var)), vars_[0]
                )
    except Exception:
        pass

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


def explain_default_model(explicit: Optional[str] = None) -> Tuple[str, str]:
    """Return ``(model, source)`` for the model a run will actually dispatch.

    Side-effect free (no persistence, no notice) so it can back introspection
    such as ``praisonai config provenance``. ``source`` is one of
    ``"explicit"``, ``"state:<path>"``, ``"env:MODEL_NAME"`` /
    ``"env:OPENAI_MODEL_NAME"``, ``"local"``, ``"provider:<ENV_VAR>"`` or
    ``"fallback"``. :func:`resolve_default_model` is built on top of this so the
    reported source can never drift from the resolution itself.
    """
    if explicit:
        return explicit, "explicit"

    recent = get_recent_model()
    if recent:
        return recent, f"state:{_model_state_path()}"

    # Honour OPENAI_MODEL_NAME / MODEL_NAME for backward compatibility before
    # falling back to credential-based inference.
    for var in ("MODEL_NAME", "OPENAI_MODEL_NAME"):
        env_model = os.environ.get(var)
        if env_model:
            return env_model, f"env:{var}"

    try:
        from praisonai_code.llm.env import (
            default_model_for_available_provider,
            has_provider_credential,
        )
        model = default_model_for_available_provider()
        # Keyless local-first: when no cloud provider credential is present,
        # prefer a reachable local OpenAI-compatible endpoint (e.g. Ollama) so
        # the first run works before any auth. The hosted-key path is untouched.
        if not has_provider_credential():
            try:
                from praisonai_code.llm.local_detect import detect_local_model
                local = detect_local_model()
            except Exception:
                local = None
            if local:
                return local.model, "local"
    except Exception:
        model = _fallback_model()

    provider = _provider_for_model(model)
    if provider and os.environ.get(provider):
        return model, f"provider:{provider}"
    return model, "fallback"


def resolve_default_model(
    explicit: Optional[str] = None,
    *,
    persist: bool = True,
    notify: bool = True,
) -> str:
    """Resolve the default model for a zero-config run.

    Precedence: ``explicit`` > recent (persisted) > ``MODEL_NAME`` /
    ``OPENAI_MODEL_NAME`` > provider-aware best > the terminal fallback
    (:data:`praisonai_code.llm.env.DEFAULT_FALLBACK_MODEL`). See
    :func:`explain_default_model` for the source of the chosen model.

    Only *user-chosen* models (``explicit`` and the env overrides) are
    persisted as the recent model. Provider-*inferred* defaults and the
    terminal fallback are intentionally **not** persisted: persisting them
    would let a stale inferred default short-circuit credential-based
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
    model, source = explain_default_model(explicit)

    if source == "explicit" or source.startswith("env:"):
        if persist:
            set_recent_model(model)
        return model

    if notify and source == "local":
        _echo(
            f"No cloud key found; using local model {model}. Run "
            f"`praisonai setup` to add a hosted provider."
        )
    elif notify and source.startswith("provider:"):
        _echo(
            f"No model set; using {model} because "
            f"{source.split(':', 1)[1]} is present."
        )

    # NOTE: provider-inferred defaults and the terminal fallback are
    # deliberately NOT persisted. Persisting them would let a stale inferred
    # default win over fresh credential-based inference on a later run when the
    # user's available providers have changed, re-introducing the very
    # zero-config failure this resolver exists to prevent.
    return model


def _echo(message: str) -> None:
    try:
        import typer
        typer.echo(message)
    except Exception:
        pass
