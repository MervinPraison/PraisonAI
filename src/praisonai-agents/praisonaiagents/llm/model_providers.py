"""Model-name → provider-id resolution.

Maps a bare model name (e.g. ``claude-sonnet-4-6``, ``llama-3.1-70b``) to its
canonical provider id (``anthropic``, ``groq``, ...). This is the single source
of truth for provider inference so callers no longer hand-code a 3-branch
``if/elif`` that silently ignores every other vendor.

Third parties add a vendor by publishing an entry point under the
``praisonaiagents.model_providers`` group. Each entry point loads a callable
``(model_name_lowercased: str) -> bool``; the entry-point *name* is the provider
id returned on a match. Registered matchers take precedence over the built-ins,
so a plugin can also override built-in detection.
"""

from __future__ import annotations

from typing import Callable, Dict, Optional

# Built-in model-name → provider matchers. Kept intentionally small and data
# driven; extend via the entry-point group rather than editing callers.
_BUILTINS: Dict[str, Callable[[str], bool]] = {
    # ``claude`` is matched as a substring so cloud-vendored forms
    # (``us.anthropic.claude-3-5-sonnet``, ``anthropic.claude-...``) still
    # resolve, preserving the pre-refactor behaviour that keyed off
    # ``'claude' in model``.
    "anthropic": lambda m: "claude" in m,
    "openai": lambda m: m.startswith(("gpt-", "o1-", "o3-", "o4-", "chatgpt-")),
    "google": lambda m: m.startswith(("gemini-", "gemma-")),
    "groq": lambda m: m.startswith(("llama-", "mixtral-", "gemma2-")) and "groq" in m,
    "cohere": lambda m: m.startswith(("command-", "c4ai-")),
    "mistral": lambda m: m.startswith(("mistral-", "codestral-", "open-mistral-", "open-mixtral-")),
    "ollama": lambda m: m.startswith("ollama/"),
    "deepseek": lambda m: m.startswith("deepseek-"),
    "xai": lambda m: m.startswith("grok-"),
    "perplexity": lambda m: m.startswith(("pplx-", "sonar-")),
}


def _entry_point_matchers():
    """Yield (provider_id, matcher) pairs registered by third-party plugins.

    Isolated so a broken plugin cannot take down provider resolution: any
    import/metadata failure yields nothing and falls back to built-ins.
    """
    try:
        from importlib.metadata import entry_points
    except Exception:  # pragma: no cover - importlib.metadata always present on 3.8+
        return

    try:
        eps = entry_points(group="praisonaiagents.model_providers")
    except TypeError:
        # Python 3.9 returns a dict-like object without the group kwarg.
        eps = entry_points().get("praisonaiagents.model_providers", [])
    except Exception:
        return

    for ep in eps:
        try:
            matcher = ep.load()
        except Exception:
            continue
        yield ep.name, matcher


def resolve_provider(model_name: str) -> Optional[str]:
    """Return the canonical provider id for ``model_name``, or None.

    Precedence:
      1. Explicit litellm-style prefix wins (``openai/gpt-4o`` -> ``openai``).
      2. Entry-point registered matchers (third-party vendors / overrides).
      3. Built-in matchers.
    """
    if not model_name:
        return None

    # 1. Explicit provider prefix.
    if "/" in model_name:
        return model_name.split("/", 1)[0].lower()

    lower = model_name.lower()

    # 2. Third-party / override matchers.
    for provider, matcher in _entry_point_matchers():
        try:
            if matcher(lower):
                return provider
        except Exception:
            continue

    # 3. Built-ins.
    for provider, matcher in _BUILTINS.items():
        if matcher(lower):
            return provider

    return None
