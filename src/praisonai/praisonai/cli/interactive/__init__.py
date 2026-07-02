"""Hybrid CLI interactive package: wrapper core/TUI + code runtime modules.

After C8 repatriation, ``core`` and ``async_tui`` live under this package.
Config, events, REPL, and frontends remain in ``praisonai_code.cli.interactive``.
"""

try:  # pragma: no cover - defensive
    import praisonai_code.cli.interactive as _code_interactive

    for _code_dir in getattr(_code_interactive, "__path__", []):
        if _code_dir not in __path__:
            __path__.append(_code_dir)
    del _code_dir
except Exception:  # pragma: no cover - code package optional at import time
    _code_interactive = None

__all__ = [
    "InteractiveCore",
    "InteractiveConfig",
    "InteractiveEvent",
    "InteractiveEventType",
    "ApprovalRequest",
    "ApprovalResponse",
    "ApprovalDecision",
]


def __getattr__(name: str):
    if name == "InteractiveCore":
        from .core import InteractiveCore

        return InteractiveCore
    if _code_interactive is not None:
        try:
            return getattr(_code_interactive, name)
        except AttributeError:
            pass
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__():
    base = set(globals().keys()) | set(__all__)
    if _code_interactive is not None:
        base |= set(dir(_code_interactive))
    return sorted(base)
