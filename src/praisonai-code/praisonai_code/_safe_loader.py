"""
Safe module loader with PRAISONAI_ALLOW_LOCAL_TOOLS opt-in.

This module provides a safe way to load user-supplied .py files with the same
security posture as tool_resolver.py. All exec_module() calls should route
through this helper to ensure consistent opt-in behavior.
"""
import importlib.util
import logging
import os
import sys
import uuid
from pathlib import Path
from types import ModuleType

logger = logging.getLogger(__name__)


class LocalToolsDisabled(RuntimeError):
    """Raised when local tools loading is disabled but required."""
    pass


def load_user_module(
    module_path: str | Path,
    *,
    name: str,
    allow_outside_cwd: bool = False,
    skip_env_check: bool = False,
) -> ModuleType | None:
    """Load a user-supplied .py file with the same opt-in tool_resolver enforces.

    Args:
        module_path: Path to the .py file to load
        name: Module name to use for the spec
        allow_outside_cwd: When True, skip the CWD boundary check. Only pass
            this for paths the user provided explicitly (e.g. a ``--tools``
            CLI argument), never for API/network-derived paths.
        skip_env_check: When True, bypass the ``PRAISONAI_ALLOW_LOCAL_TOOLS``
            environment gate for this single, in-process call. This is the
            thread-safe way for an explicit-load caller to authorize a load it
            already trusts, without mutating the process-wide env var (which
            would leak the authorization to concurrent threads). Only pass this
            for paths the caller provided explicitly, never for
            API/network-derived paths.

    Returns:
        Loaded module or None if loading is disabled or the file is missing.

    Raises:
        LocalToolsDisabled: If caller wants strict behavior when disabled.
    """
    if not skip_env_check and os.environ.get("PRAISONAI_ALLOW_LOCAL_TOOLS", "").lower() != "true":
        logger.warning(
            "Refusing to exec %s: set PRAISONAI_ALLOW_LOCAL_TOOLS=true to enable.",
            module_path,
        )
        return None

    path = Path(module_path).resolve()
    if not path.is_file():
        return None

    # Enforce that the path is under CWD to prevent ../-style traversal from
    # API/network inputs. Explicit user-provided files may opt out.
    if not allow_outside_cwd:
        cwd = Path.cwd().resolve()
        try:
            path.relative_to(cwd)
        except ValueError:
            logger.warning("Refusing to exec %s: outside working directory.", path)
            return None

    # Namespace the sys.modules entry per-load so two concurrent user-tool
    # loads on the same process (e.g. multi-tenant ``praisonai serve``) cannot
    # clobber one another through a shared, fixed module name — and a failed
    # exec can only pop *its own* entry, never another live tenant's module.
    # ``name`` is retained only as a readable hint in the qualified key; every
    # reachable caller binds the returned module object rather than reading
    # ``sys.modules[name]``.
    qualified = f"praisonai_userload::{name}::{path}::{uuid.uuid4().hex}"
    spec = importlib.util.spec_from_file_location(qualified, str(path))
    if spec is None or spec.loader is None:
        return None

    module = importlib.util.module_from_spec(spec)
    # Register before exec so decorators/dataclasses that consult
    # sys.modules[__name__] during module execution resolve correctly.
    sys.modules[qualified] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        sys.modules.pop(qualified, None)
        raise
    return module


def load_user_module_strict(module_path: str | Path, *, name: str) -> ModuleType:
    """Load a user-supplied .py file, raising LocalToolsDisabled if disabled.

    Args:
        module_path: Path to the .py file to load
        name: Module name to use for the spec

    Returns:
        Loaded module

    Raises:
        LocalToolsDisabled: If PRAISONAI_ALLOW_LOCAL_TOOLS is not set to 'true'
        FileNotFoundError: If the file doesn't exist
    """
    if os.environ.get("PRAISONAI_ALLOW_LOCAL_TOOLS", "").lower() != "true":
        raise LocalToolsDisabled(
            f"Refusing to exec {module_path}: set PRAISONAI_ALLOW_LOCAL_TOOLS=true to enable."
        )

    path = Path(module_path).resolve()
    if not path.is_file():
        raise FileNotFoundError(f"Module file not found: {path}")

    # Security: enforce that the path is under CWD
    cwd = Path.cwd().resolve()
    try:
        path.relative_to(cwd)
    except ValueError:
        raise LocalToolsDisabled(
            f"Refusing to exec {path}: outside working directory."
        ) from None

    # Per-load-unique sys.modules key: see load_user_module for the rationale
    # (multi-tenant / concurrent-load isolation; failed exec pops only its own
    # entry). Callers bind the returned module rather than sys.modules[name].
    qualified = f"praisonai_userload::{name}::{path}::{uuid.uuid4().hex}"
    spec = importlib.util.spec_from_file_location(qualified, str(path))
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not create spec for {path}")

    module = importlib.util.module_from_spec(spec)
    sys.modules[qualified] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        sys.modules.pop(qualified, None)
        raise
    return module