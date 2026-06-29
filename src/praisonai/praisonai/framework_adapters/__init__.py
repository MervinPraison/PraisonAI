# Framework adapters for protocol-driven architecture.
#
# Adapter classes are intentionally NOT eagerly imported here so that the lazy
# loaders in ``registry.py`` remain effective and importing the package does not
# drag in optional framework dependencies. Prefer:
#
#     from praisonai.framework_adapters.registry import get_default_registry
#
# Adapter classes remain importable from the package surface via PEP 562
# ``__getattr__`` for backward compatibility; the import cost is paid only on
# first attribute access.
import warnings

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

# name -> (submodule, attribute). Loaded lazily on first access.
_LAZY_ATTRS = {
    "FrameworkAdapter": (".base", "FrameworkAdapter"),
    "BaseFrameworkAdapter": (".base", "BaseFrameworkAdapter"),
    "scoped_telemetry_disable": (".base", "scoped_telemetry_disable"),
    "CrewAIAdapter": (".crewai_adapter", "CrewAIAdapter"),
    "AutoGenAdapter": (".autogen_adapter", "AutoGenAdapter"),
    "AutoGenV4Adapter": (".autogen_adapter", "AutoGenV4Adapter"),
    "AG2Adapter": (".autogen_adapter", "AG2Adapter"),
    "PraisonAIAdapter": (".praisonai_adapter", "PraisonAIAdapter"),
    "get_default_registry": (".registry", "get_default_registry"),
    "get_install_hint": (".registry", "get_install_hint"),
    "list_framework_choices": (".registry", "list_framework_choices"),
}

# Optional, framework-specific adapters emit a deprecation warning on access.
_DEPRECATED = {
    "CrewAIAdapter",
    "AutoGenAdapter",
    "AutoGenV4Adapter",
    "AG2Adapter",
}

_DEPRECATION = (
    "Importing {name} from praisonai.framework_adapters is deprecated; "
    "install praisonai-frameworks or use FrameworkAdapterRegistry entry points."
)


def __getattr__(name):
    target = _LAZY_ATTRS.get(name)
    if target is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    if name in _DEPRECATED:
        warnings.warn(_DEPRECATION.format(name=name), DeprecationWarning, stacklevel=2)
    from importlib import import_module

    module = import_module(target[0], __name__)
    value = getattr(module, target[1])
    globals()[name] = value
    return value


def __dir__():
    return sorted(set(globals()) | set(_LAZY_ATTRS))
