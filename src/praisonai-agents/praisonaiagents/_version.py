"""
Version utilities for praisonaiagents package.

This module provides version information by reading from pyproject.toml
to avoid duplication and ensure the single source of truth.
"""

import re
from pathlib import Path


def get_version() -> str:
    """
    Get the version string from pyproject.toml.
    
    Returns:
        str: Version string (e.g., "1.6.52")
        
    Raises:
        RuntimeError: If version cannot be found or parsed
    """
    try:
        # Get the package root (praisonaiagents directory)
        package_root = Path(__file__).parent
        # Go up to src/praisonai-agents directory
        pyproject_path = package_root.parent / "pyproject.toml"
        
        if not pyproject_path.exists():
            raise RuntimeError(f"pyproject.toml not found at {pyproject_path}")
            
        content = pyproject_path.read_text()
        
        # Look for version = "X.Y.Z" pattern
        match = re.search(r'version\s*=\s*["\']([^"\']+)["\']', content)
        if not match:
            raise RuntimeError("Version not found in pyproject.toml")
            
        return match.group(1)
        
    except Exception as e:
        # Fallback to "unknown" to avoid breaking imports
        import warnings
        warnings.warn(
            f"Failed to read version from pyproject.toml: {e}. Using 'unknown'.",
            RuntimeWarning
        )
        return "unknown"


# Cache the version to avoid reading the file multiple times
__version__ = get_version()