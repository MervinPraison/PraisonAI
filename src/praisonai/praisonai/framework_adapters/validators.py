"""
Framework availability validators.

Provides early validation of framework availability to fail fast at CLI entry
rather than inside run() methods after expensive setup work.
"""

from .registry import get_default_registry, get_install_hint


def assert_framework_available(name: str, *, registry=None) -> None:
    """
    Raise ImportError immediately if the chosen framework is missing.

    Args:
        name: Framework name to validate
        registry: Optional adapter registry to consult. When omitted, the
            process-default registry is used. Passing the caller's injected
            registry keeps DI intact so a scoped/per-tenant adapter is not
            rejected just because it is absent from the process default.

    Raises:
        ImportError: If framework is not available with actionable install hint
    """
    registry = registry or get_default_registry()

    if not registry.is_available(name):
        hint = get_install_hint(name, registry=registry)
        raise ImportError(
            f"Framework '{name}' was requested but is not installed.\n"
            f"Install it with:\n    {hint}"
        )
