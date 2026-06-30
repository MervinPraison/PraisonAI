# Framework adapters for protocol-driven architecture
import warnings

from .base import FrameworkAdapter, BaseFrameworkAdapter, scoped_telemetry_disable
from .praisonai_adapter import PraisonAIAdapter
from .registry import (
    get_default_registry,
    get_install_hint,
    list_framework_choices,
)

__all__ = [
    "FrameworkAdapter",
    "BaseFrameworkAdapter",
    "scoped_telemetry_disable",
    "CrewAIAdapter",
    "AutoGenAdapter",
    "AutoGenV4Adapter",
    "AG2Adapter",
    "PraisonAIAdapter",
    "get_default_registry",
    "get_install_hint",
    "list_framework_choices",
]

_DEPRECATION = (
    "Importing {name} from praisonai.framework_adapters is deprecated; "
    "install praisonai-frameworks or use FrameworkAdapterRegistry entry points."
)


def __getattr__(name: str):
    if name == "CrewAIAdapter":
        warnings.warn(_DEPRECATION.format(name="CrewAIAdapter"), DeprecationWarning, stacklevel=2)
        from .crewai_adapter import CrewAIAdapter
        return CrewAIAdapter
    if name == "AutoGenAdapter":
        warnings.warn(_DEPRECATION.format(name="AutoGenAdapter"), DeprecationWarning, stacklevel=2)
        from .autogen_adapter import AutoGenAdapter
        return AutoGenAdapter
    if name == "AutoGenV4Adapter":
        warnings.warn(_DEPRECATION.format(name="AutoGenV4Adapter"), DeprecationWarning, stacklevel=2)
        from .autogen_adapter import AutoGenV4Adapter
        return AutoGenV4Adapter
    if name == "AG2Adapter":
        warnings.warn(_DEPRECATION.format(name="AG2Adapter"), DeprecationWarning, stacklevel=2)
        from .autogen_adapter import AG2Adapter
        return AG2Adapter
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
