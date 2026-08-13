"""Back-compat interactive package: forwards to ``praisonai_code.cli.interactive``.

The full interactive experience (``core``, ``async_tui``, ``config``, ``events``,
REPL, frontends) is resident in ``praisonai_code.cli.interactive`` so
``pip install praisonai-code`` alone yields a working interactive ``chat``/``code``
session. This package keeps the old ``praisonai.cli.interactive.*`` import paths
working via lightweight shims that preserve module identity.
"""

try:  # pragma: no cover - defensive
    import praisonai_code.cli.interactive as _code_interactive

    for _code_dir in getattr(_code_interactive, "__path__", []):
        if _code_dir not in __path__:
            __path__.append(_code_dir)
except ImportError:  # pragma: no cover - code package optional at import time
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
