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


# Closed-weights model families that no local runtime can serve. Used to stop a
# local ``base_url`` (an OpenAI-compatible proxy on :11434, say) from being read
# as "this is an Ollama model".
#
# Open-weights families are deliberately ABSENT -- gemma, llama, mistral, qwen,
# deepseek and phi are all routinely served by Ollama, so they must stay
# eligible for URL-based local detection. That is why this is a separate, much
# narrower predicate than ``resolve_provider``: the latter maps ``gemma-`` to
# "google" and ``mistral-`` to "mistral", which is correct for provider routing
# and wrong for deciding whether a model could be running locally.
HOSTED_ONLY_PREFIXES = ("gpt-", "o1-", "o3-", "o4-", "chatgpt-", "claude", "gemini-")


def is_hosted_only_model(model_name: str) -> bool:
    """True if ``model_name`` names a closed-weights model no local server hosts.

    Every route segment is tested, so single-prefix (``openai/gpt-4o``), nested
    (``openrouter/openai/gpt-4o``, ``openrouter/anthropic/claude-*``) and
    vendor-qualified (``bedrock/anthropic.claude-*``, ``us.anthropic.claude-*``)
    forms all resolve to the hosted family they name -- mirroring the substring
    fallback that ``_detect_provider`` uses for the same routed models. An
    open-weights model reached over the OpenAI-compatible route
    (``openai/qwen3:0.6b``) is not hosted-only and keeps its local treatment,
    because the prefixes tested are themselves closed-weights families no local
    runtime serves.
    """
    if not model_name:
        return False
    lower = model_name.lower()
    # Split on both route ("/") and vendor-qualifier (".") boundaries so a
    # family name anywhere in the path is seen: bedrock/anthropic.claude-3 ->
    # ["bedrock", "anthropic", "claude-3"].
    for segment in lower.replace(".", "/").split("/"):
        if segment.startswith(HOSTED_ONLY_PREFIXES):
            return True
    return False


# The small helper model used for internal auxiliary calls -- memory quality
# scoring, context compaction, session titling, workflow routing. Historically
# about a dozen sites resolved this from OPENAI_MODEL_NAME while about twenty
# more hardcoded the same string, so half of them could not be pointed anywhere
# else. That, not the endpoint, is what blocks running fully locally: litellm and
# the openai SDK both honour OPENAI_BASE_URL, so those sites do reach a local
# server -- and then ask it for a model no local server serves.
DEFAULT_AUXILIARY_MODEL = "gpt-4o-mini"


def default_auxiliary_model(explicit: Optional[str] = None) -> str:
    """Resolve the model to use for an internal auxiliary LLM call.

    Precedence: an explicit argument, then PRAISONAI_AUXILIARY_MODEL, then
    OPENAI_MODEL_NAME, then DEFAULT_AUXILIARY_MODEL.

    PRAISONAI_AUXILIARY_MODEL exists because a local setup often wants a
    *smaller* model for helper calls than for the agent itself -- pointing
    OPENAI_MODEL_NAME at a 70B local model should not make every internal
    summarisation call use it.
    """
    if explicit:
        return explicit
    import os
    for var in ("PRAISONAI_AUXILIARY_MODEL", "OPENAI_MODEL_NAME"):
        value = (os.environ.get(var) or "").strip()
        if value:
            return value
    return DEFAULT_AUXILIARY_MODEL


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
