"""Hybrid TUI package: wrapper app + code widgets/screens."""

try:  # pragma: no cover - defensive
    import praisonai_code.cli.features.tui as _code_tui

    for _code_dir in getattr(_code_tui, "__path__", []):
        if _code_dir not in __path__:
            __path__.append(_code_dir)
except ImportError:  # pragma: no cover - code package optional at import time
    _code_tui = None

if _code_tui is not None:
    __all__ = list(getattr(_code_tui, "__all__", []))

    def __getattr__(name: str):
        return getattr(_code_tui, name)

    def __dir__():
        return sorted(set(globals().keys()) | set(dir(_code_tui)))
