"""Version helpers for praisonai-code (wrapper-independent)."""

from __future__ import annotations

from typing import Optional


def get_package_version() -> str:
    """Return the installed ``praisonai-code`` version string."""
    try:
        from importlib.metadata import version

        return str(version("praisonai-code"))
    except Exception:
        from praisonai_code import __version__

        return __version__


def get_wrapper_version() -> Optional[str]:
    """Return the installed ``praisonai`` wrapper version, if present."""
    try:
        from importlib.metadata import version

        return str(version("praisonai"))
    except Exception:
        try:
            from praisonai_code._wrapper_bridge import import_wrapper_module
            _mod = import_wrapper_module('praisonai.version')
            wrapper_version = getattr(_mod, '__version__')

            return str(wrapper_version)
        except Exception:
            return None
