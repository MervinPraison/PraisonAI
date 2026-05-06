"""
Framework availability validators.

Provides early validation of framework availability to fail fast at CLI entry
rather than inside run() methods after expensive setup work.
"""

from typing import NoReturn
from .registry import FrameworkAdapterRegistry


# Install hints for common frameworks
_INSTALL_HINTS = {
    "crewai": "pip install 'praisonai[crewai]'   # or: pip install crewai",
    "autogen": "pip install 'praisonai[autogen]'  # or: pip install pyautogen",
    "praisonai": "pip install praisonaiagents",
}


def assert_framework_available(name: str) -> None:
    """
    Raise ImportError immediately if the chosen framework is missing.
    
    Args:
        name: Framework name to validate
        
    Raises:
        ImportError: If framework is not available with actionable install hint
    """
    registry = FrameworkAdapterRegistry.get_instance()
    
    if not registry.is_available(name):
        hint = _INSTALL_HINTS.get(name, f"pip install {name}")
        raise ImportError(
            f"Framework '{name}' was requested but is not installed.\n"
            f"Install it with:\n    {hint}"
        )