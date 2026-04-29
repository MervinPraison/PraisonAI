"""
Safe module loader with PRAISONAI_ALLOW_LOCAL_TOOLS opt-in.

This module provides a safe way to load user-supplied .py files with the same
security posture as tool_resolver.py. All exec_module() calls should route
through this helper to ensure consistent opt-in behavior.
"""
import importlib.util
import logging
import os
from pathlib import Path
from types import ModuleType

logger = logging.getLogger(__name__)


class LocalToolsDisabled(RuntimeError):
    """Raised when local tools loading is disabled but required."""
    pass


def load_user_module(module_path: str | Path, *, name: str) -> ModuleType | None:
    """Load a user-supplied .py file with the same opt-in tool_resolver enforces.

    Args:
        module_path: Path to the .py file to load
        name: Module name to use for the spec

    Returns:
        Loaded module or None if loading is disabled or the file is missing.

    Raises:
        LocalToolsDisabled: If caller wants strict behavior when disabled.
    """
    if os.environ.get("PRAISONAI_ALLOW_LOCAL_TOOLS", "").lower() != "true":
        logger.warning(
            "Refusing to exec %s: set PRAISONAI_ALLOW_LOCAL_TOOLS=true to enable.",
            module_path,
        )
        return None

    path = Path(module_path).resolve()
    if not path.is_file():
        return None

    # Optional: enforce that the path is under CWD or an explicit allowlist
    # to prevent ../-style traversal from API/network inputs.
    cwd = Path.cwd().resolve()
    if not str(path).startswith(str(cwd) + os.sep):
        logger.warning("Refusing to exec %s: outside working directory.", path)
        return None

    spec = importlib.util.spec_from_file_location(name, str(path))
    if spec is None or spec.loader is None:
        return None
    
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
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
    if not str(path).startswith(str(cwd) + os.sep):
        raise LocalToolsDisabled(f"Refusing to exec {path}: outside working directory.")

    spec = importlib.util.spec_from_file_location(name, str(path))
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not create spec for {path}")
    
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module