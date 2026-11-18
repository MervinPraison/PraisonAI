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
    except (OSError, ValueError):  # ValueError covers UnicodeDecodeError
        return None
    # Only look inside the [project] table so [tool.*] or other tables
    # cannot supply the name or version.
    section = re.search(r"^\[project\][ \t]*$(.*?)(?=^\[|\Z)", content, re.MULTILINE | re.DOTALL)
    if not section:
        return None
    body = section.group(1)
    # Only trust the file if it declares this distribution's name.
    if not re.search(r'^\s*name\s*=\s*["\']' + _DIST_NAME + r'["\']\s*$', body, re.MULTILINE):
        return None
    match = re.search(r'^\s*version\s*=\s*["\']([^"\']+)["\']', body, re.MULTILINE)
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
        from importlib.metadata import version as dist_version
        return dist_version(_DIST_NAME)
    except Exception:  # PackageNotFoundError or broken metadata
        import logging
        logging.getLogger(__name__).debug(
            "Could not read %s distribution metadata", _DIST_NAME, exc_info=True)
    import warnings
    warnings.warn(
        "Could not determine praisonaiagents version from pyproject.toml or "
        "installed distribution metadata. Using 'unknown'.",
        RuntimeWarning,
    )
    return "unknown"


# Cache the version to avoid reading the file multiple times
__version__ = get_version()
