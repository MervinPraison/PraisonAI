# Lazy availability checks using find_spec (no actual import)
# This avoids the ~3200ms crewai import at CLI startup
import importlib.util

CREWAI_AVAILABLE = importlib.util.find_spec("crewai") is not None
AUTOGEN_AVAILABLE = importlib.util.find_spec("autogen") is not None
PRAISONAI_TOOLS_AVAILABLE = False

# Lazy import helper - only imports when actually needed
def _get_autogen_tools():
    """Lazy import autogen_tools only when needed."""
    global PRAISONAI_TOOLS_AVAILABLE
    if CREWAI_AVAILABLE or AUTOGEN_AVAILABLE:
        try:
            from . import autogen_tools
            PRAISONAI_TOOLS_AVAILABLE = True
            return autogen_tools
        except ImportError:
            pass
    return None

# For backward compatibility, provide __getattr__ for lazy access
def __getattr__(name):
    """Lazy load autogen_tools exports on demand."""
    tools_module = _get_autogen_tools()
    if tools_module and hasattr(tools_module, name):
        return getattr(tools_module, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")