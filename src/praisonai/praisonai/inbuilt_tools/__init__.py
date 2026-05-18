"""Lazy access to autogen_tools, with `find_spec` startup probes for crewai/autogen."""
import importlib.util
from praisonai.auto import _load_optional

CREWAI_AVAILABLE = importlib.util.find_spec("crewai") is not None
AUTOGEN_AVAILABLE = importlib.util.find_spec("autogen") is not None


def _load_autogen_tools():
    if not (CREWAI_AVAILABLE or AUTOGEN_AVAILABLE):
        return None
    # importlib.import_module avoids the `from . import` recursion footgun.
    import importlib
    return importlib.import_module(__name__ + ".autogen_tools")


def _get_autogen_tools():
    """Thread-safe, single-shot lazy import. Negative result is cached too."""
    return _load_optional("inbuilt_autogen_tools", _load_autogen_tools)


def _praisonai_tools_available() -> bool:
    """Read-only accessor — never mutate this from inside a function."""
    return _get_autogen_tools() is not None


# Backward-compat: keep the constant, computed lazily on attribute access.
def __getattr__(name):
    if name == "PRAISONAI_TOOLS_AVAILABLE":
        return _praisonai_tools_available()
    tools_module = _get_autogen_tools()
    if tools_module is not None and hasattr(tools_module, name):
        return getattr(tools_module, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")