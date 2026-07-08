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
    """Return the installed ``praisonai`` wrapper version, if present.

    Prefer the source ``praisonai.version.__version__`` (resolved lazily via the
    wrapper bridge) so that editable installs report the same version as
    ``praisonai --version`` even when the installed package metadata is stale.
    Fall back to package metadata when the source module is unavailable.
    """
    try:
        from praisonai_code._wrapper_bridge import import_wrapper_module

        wrapper_version = getattr(import_wrapper_module("praisonai.version"), "__version__")

        return str(wrapper_version)
    except Exception:
        pass

    try:
        from importlib.metadata import version

        return str(version("praisonai"))
    except Exception:
        return None
