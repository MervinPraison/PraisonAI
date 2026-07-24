"""Lazy optional access to the ``praisonai`` wrapper from ``praisonai-code``.

Agentic CLI modules use this for wrapper-only features (bots, gateway, training,
framework adapters). Standalone ``pip install praisonai-code`` works for terminal
agent commands; wrapper imports fail with a clear install hint.
"""

from __future__ import annotations

import importlib
from pathlib import Path
from types import ModuleType
from typing import Any, Optional, TypeVar

T = TypeVar("T")

_INSTALL_HINT = "Install the full wrapper: pip install praisonai"


def wrapper_available() -> bool:
    """Return True when the ``praisonai`` wrapper package is importable."""
    import importlib.util

    return importlib.util.find_spec("praisonai") is not None


def wrapper_package_path() -> Optional[Path]:
    """Return the on-disk directory of the installed ``praisonai`` wrapper.

    Resolves the wrapper package location without importing it, so callers can
    reach bundled wrapper assets (e.g. ``ui_*/default_app.py`` presets) that live
    beside the wrapper rather than in ``praisonai_code``. Returns ``None`` when the
    wrapper is not installed so callers can guide the user to ``pip install``.
    """
    import importlib.util

    spec = importlib.util.find_spec("praisonai")
    if spec is None or not spec.submodule_search_locations:
        return None
    return Path(spec.submodule_search_locations[0])


def import_wrapper_module(name: str) -> ModuleType:
    """Import ``praisonai.*`` or raise with an install hint."""
    if not name.startswith("praisonai"):
        raise ValueError(f"Expected praisonai module name, got {name!r}")
    try:
        return importlib.import_module(name)
    except ImportError as exc:
        raise ImportError(f"{name} requires the praisonai wrapper. {_INSTALL_HINT}") from exc


def get_wrapper_attr(module_name: str, attr: str) -> Any:
    """Import a wrapper module and return one attribute."""
    return getattr(import_wrapper_module(module_name), attr)


def optional_wrapper_attr(module_name: str, attr: str, default: T | None = None) -> Any | T | None:
    """Return a wrapper attribute when installed, else ``default``.

    Falls back to ``default`` when the wrapper package is missing (ImportError)
    or when an installed wrapper module lacks the requested attribute
    (AttributeError), so callers degrade gracefully in both cases.
    """
    if not wrapper_available():
        return default
    try:
        return get_wrapper_attr(module_name, attr)
    except (ImportError, AttributeError):
        return default


def run_wrapper_command(argv: list[str], *, feature: str) -> None:
    """Re-enter the legacy ``PraisonAI().main()`` for a wrapper-resident command.

    Typer stub commands (``agents``, ``workflow``, ``registry`` and peers) still
    dispatch to the legacy CLI by mutating ``sys.argv`` and calling
    ``PraisonAI().main()``. On a standalone ``pip install praisonai-code`` the
    legacy path imports ``praisonai.cli.legacy.dispatch.argparse_builder`` which
    is wrapper-only, so it raises a Rich ``ImportError`` traceback before any
    feature handler runs (issue #2837).

    This helper guards that re-entry: when the ``praisonai`` wrapper is not
    installed it fails fast with a single-line install hint (exit code 1) instead
    of a traceback. When the wrapper is present it performs the ``sys.argv``
    mutation + ``main()`` call exactly as before, restoring ``sys.argv`` after.
    A clean ``SystemExit`` (code ``0``/``None``) is swallowed so the calling
    Typer command returns normally, while any non-zero exit code is re-raised so
    the shell sees the wrapper's failure.

    Args:
        argv: Legacy argv tokens (e.g. ``["agents", "list"]``) without the
            leading program name.
        feature: Command group name used in the standalone hint message.
    """
    import sys

    if not wrapper_available():
        print(
            f"{feature} requires the full wrapper. {_INSTALL_HINT}",
            file=sys.stderr,
        )
        raise SystemExit(1)

    from praisonai_code.cli.main import PraisonAI

    original_argv = sys.argv
    sys.argv = ["praisonai"] + argv
    try:
        PraisonAI().main()
    except SystemExit as exc:
        if exc.code:
            raise
    finally:
        sys.argv = original_argv
