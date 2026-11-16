"""
Version utilities for praisonaiagents package.

In a source checkout the version is read from this project's pyproject.toml
(single source of truth). For installed wheels, the distribution metadata is
used instead, since the parent directory is site-packages and any
pyproject.toml found there belongs to an unrelated project.
"""

import re
from pathlib import Path

_DIST_NAME = "praisonaiagents"


def _version_from_source_tree():
    """Return the version from the sibling pyproject.toml if it is ours."""
    pyproject_path = Path(__file__).resolve().parent.parent / "pyproject.toml"
    try:
        content = pyproject_path.read_text(encoding="utf-8")
    except OSError:
        return None
    # Only trust the file if it declares this distribution's name.
    if not re.search(
        r'^\s*name\s*=\s*["\']' + _DIST_NAME + r'["\']', content, re.MULTILINE
    ):
        return None
    match = re.search(r'^\s*version\s*=\s*["\']([^"\']+)["\']', content, re.MULTILINE)
    return match.group(1) if match else None


def get_version() -> str:
    """
    Get the praisonaiagents version string.

    Returns:
        str: Version string (e.g., "1.6.52"), or "unknown" if undeterminable.
    """
    version = _version_from_source_tree()
    if version:
        return version
    try:
        from importlib.metadata import PackageNotFoundError, version as dist_version
        try:
            return dist_version(_DIST_NAME)
        except PackageNotFoundError:
            pass
    except Exception:
        pass
    import warnings
    warnings.warn(
        "Could not determine praisonaiagents version from pyproject.toml or "
        "installed distribution metadata. Using 'unknown'.",
        RuntimeWarning,
    )
    return "unknown"


# Cache the version to avoid reading the file multiple times
__version__ = get_version()
