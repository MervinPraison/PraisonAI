"""
PraisonAI Templates Module

Provides template loading, caching, and resolution for Agent/Workflow configurations.
All imports are lazy to ensure zero performance impact when not used.
"""

__all__ = [
    "TemplateLoader",
    "TemplateResolver",
    "TemplateCache",
    "TemplateRegistry",
    "TemplateSecurity",
    "TemplateDiscovery",
    "DiscoveredTemplate",
    "DependencyChecker",
    "StrictModeError",
    "ToolsDoctor",
    "ToolOverrideLoader",
    "SecurityError",
    "load_template",
    "list_templates",
    "search_templates",
    "install_template",
    "clear_cache",
    "discover_templates",
    "find_template_path",
]

# Lazy loading implementation
_module_cache = {}


def __getattr__(name):
    """Lazy load template components to avoid import overhead."""
    if name in _module_cache:
        return _module_cache[name]
    
    if name == "TemplateLoader":
        from .loader import TemplateLoader
        _module_cache[name] = TemplateLoader
        return TemplateLoader
    elif name == "TemplateResolver":
        from .resolver import TemplateResolver
        _module_cache[name] = TemplateResolver
        return TemplateResolver
    elif name == "TemplateCache":
        from .cache import TemplateCache
        _module_cache[name] = TemplateCache
        return TemplateCache
    elif name == "TemplateRegistry":
        from .registry import TemplateRegistry
        _module_cache[name] = TemplateRegistry
        return TemplateRegistry
    elif name == "TemplateSecurity":
        from .security import TemplateSecurity
        _module_cache[name] = TemplateSecurity
        return TemplateSecurity
    elif name == "load_template":
        from .loader import load_template
        _module_cache[name] = load_template
        return load_template
    elif name == "list_templates":
        from .registry import list_templates
        _module_cache[name] = list_templates
        return list_templates
    elif name == "search_templates":
        from .registry import search_templates
        _module_cache[name] = search_templates
        return search_templates
    elif name == "install_template":
        from .registry import install_template
        _module_cache[name] = install_template
        return install_template
    elif name == "clear_cache":
        from .cache import clear_cache
        _module_cache[name] = clear_cache
        return clear_cache
    elif name == "TemplateDiscovery":
        from .discovery import TemplateDiscovery
        _module_cache[name] = TemplateDiscovery
        return TemplateDiscovery
    elif name == "DiscoveredTemplate":
        from .discovery import DiscoveredTemplate
        _module_cache[name] = DiscoveredTemplate
        return DiscoveredTemplate
    elif name == "discover_templates":
        from .discovery import discover_templates
        _module_cache[name] = discover_templates
        return discover_templates
    elif name == "find_template_path":
        from .discovery import find_template_path
        _module_cache[name] = find_template_path
        return find_template_path
    elif name == "DependencyChecker":
        from .dependency_checker import DependencyChecker
        _module_cache[name] = DependencyChecker
        return DependencyChecker
    elif name == "StrictModeError":
        from .dependency_checker import StrictModeError
        _module_cache[name] = StrictModeError
        return StrictModeError
    elif name == "ToolsDoctor":
        from .tools_doctor import ToolsDoctor
        _module_cache[name] = ToolsDoctor
        return ToolsDoctor
    elif name == "ToolOverrideLoader":
        from .tool_override import ToolOverrideLoader
        _module_cache[name] = ToolOverrideLoader
        return ToolOverrideLoader
    elif name == "SecurityError":
        from .tool_override import SecurityError
        _module_cache[name] = SecurityError
        return SecurityError
    
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
