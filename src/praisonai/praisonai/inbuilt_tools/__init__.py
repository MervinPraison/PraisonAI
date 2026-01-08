# Lazy availability checks using find_spec (no actual import)
# This avoids the ~3200ms crewai import at CLI startup
import importlib.util

CREWAI_AVAILABLE = importlib.util.find_spec("crewai") is not None
AUTOGEN_AVAILABLE = importlib.util.find_spec("autogen") is not None
PRAISONAI_TOOLS_AVAILABLE = False

# Guard against recursive imports
_importing_autogen_tools = False
_autogen_tools_module = None

# Lazy import helper - only imports when actually needed
def _get_autogen_tools():
    """Lazy import autogen_tools only when needed."""
    global PRAISONAI_TOOLS_AVAILABLE, _importing_autogen_tools, _autogen_tools_module
    
    # Return cached module if already imported
    if _autogen_tools_module is not None:
        return _autogen_tools_module
    
    # Prevent recursive import
    if _importing_autogen_tools:
        return None
    
    if CREWAI_AVAILABLE or AUTOGEN_AVAILABLE:
        try:
            _importing_autogen_tools = True
            from . import autogen_tools
            _autogen_tools_module = autogen_tools
            PRAISONAI_TOOLS_AVAILABLE = True
            return autogen_tools
        except ImportError:
            pass
        finally:
            _importing_autogen_tools = False
    return None

# For backward compatibility, provide __getattr__ for lazy access
def __getattr__(name):
    """Lazy load autogen_tools exports on demand."""
    # Avoid recursion during import
    if _importing_autogen_tools:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    
    tools_module = _get_autogen_tools()
    if tools_module and hasattr(tools_module, name):
        return getattr(tools_module, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")