"""Lazy access to autogen_tools, with `find_spec` startup probes for crewai/autogen."""
from praisonai.auto import _load_optional

from .._framework_availability import is_available
CREWAI_AVAILABLE = is_available("crewai")
AUTOGEN_AVAILABLE = is_available("autogen")
PRAISONAI_TOOLS_PACKAGE_AVAILABLE = is_available("praisonai_tools")


def _load_autogen_tools():
    # Load the autogen_tools module unconditionally since it can work with just praisonai_tools
    import importlib
    return importlib.import_module(__name__ + ".autogen_tools")


def _get_autogen_tools():
    """Thread-safe, single-shot lazy import. Negative result is cached too."""
    return _load_optional("inbuilt_autogen_tools", _load_autogen_tools)


def _praisonai_tools_available() -> bool:
    """Read-only accessor — never mutate this from inside a function."""
    return PRAISONAI_TOOLS_PACKAGE_AVAILABLE or _get_autogen_tools() is not None


# Backward-compat: keep the constant, computed lazily on attribute access.
def __getattr__(name):
    if name == "PRAISONAI_TOOLS_AVAILABLE":
        return _praisonai_tools_available()
    tools_module = _get_autogen_tools()
    if tools_module is not None and hasattr(tools_module, name):
        return getattr(tools_module, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
