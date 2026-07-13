"""Model-family-aware agent harness.

Selects, by model id/family, a base/harness system-prompt fragment and a
preferred file-edit format (string-replace ``edit_file`` vs ``apply_patch``).

The default profile reproduces the current generic behaviour exactly, so
behaviour is unchanged when no family match applies. The registry is
data-driven and overridable; resolution is lazy with zero import-time cost.

Usage::

    from praisonaiagents.model_harness import resolve_harness

    profile = resolve_harness("claude-opus-4")
    profile.base_prompt          # optional prompt fragment (str or None)
    profile.preferred_edit_format  # "apply_patch" | "edit_file" | None
"""

from praisonaiagents._lazy import create_lazy_getattr

_LAZY_IMPORTS = {
    "HarnessProfile": ("praisonaiagents.model_harness.profiles", "HarnessProfile"),
    "HarnessResolverProtocol": (
        "praisonaiagents.model_harness.profiles",
        "HarnessResolverProtocol",
    ),
    "resolve_harness": ("praisonaiagents.model_harness.profiles", "resolve_harness"),
    "register_profile": (
        "praisonaiagents.model_harness.profiles",
        "register_profile",
    ),
    "DEFAULT_PROFILE": (
        "praisonaiagents.model_harness.profiles",
        "DEFAULT_PROFILE",
    ),
}

__all__ = list(_LAZY_IMPORTS.keys())

__getattr__ = create_lazy_getattr(_LAZY_IMPORTS, __name__)
