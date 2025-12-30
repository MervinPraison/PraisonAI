"""
Registry Bridge Adapter

Bridges praisonaiagents.tools registry/lazy TOOL_MAPPINGS into
praisonai.mcp_server registry WITHOUT duplicating tool definitions
or importing tools eagerly.

This adapter:
- Enumerates available tools (metadata only)
- Loads tool handler lazily on first call
- Handles name collisions with clear errors
- Is optional and safe-by-default
"""

import logging
from typing import Any, Callable, Dict, List, Optional, Set

logger = logging.getLogger(__name__)

# Track registered tools to avoid duplicates
_registered_tools: Set[str] = set()
_bridge_enabled: bool = False


def is_bridge_available() -> bool:
    """Check if praisonaiagents.tools is available."""
    try:
        import importlib.util
        spec = importlib.util.find_spec("praisonaiagents.tools")
        return spec is not None
    except (ImportError, ModuleNotFoundError):
        return False


def get_tool_mappings() -> Dict[str, Any]:
    """Get TOOL_MAPPINGS from praisonaiagents.tools."""
    try:
        from praisonaiagents.tools import TOOL_MAPPINGS
        return TOOL_MAPPINGS
    except ImportError:
        return {}


def _create_lazy_handler(module_path: str, class_name: Optional[str], tool_name: str) -> Callable:
    """
    Create a lazy handler that imports the tool only when called.
    
    Args:
        module_path: Python module path
        class_name: Optional class name within module
        tool_name: Tool name for error messages
        
    Returns:
        Callable that lazily loads and executes the tool
    """
    _cached_handler = None
    
    def lazy_handler(**kwargs) -> Any:
        nonlocal _cached_handler
        
        if _cached_handler is None:
            try:
                import importlib
                mod = importlib.import_module(module_path)
                
                if class_name:
                    tool_class = getattr(mod, class_name)
                    tool_instance = tool_class()
                    if hasattr(tool_instance, 'run'):
                        _cached_handler = tool_instance.run
                    elif hasattr(tool_instance, '__call__'):
                        _cached_handler = tool_instance
                    else:
                        raise AttributeError(f"Tool class {class_name} has no run or __call__ method")
                else:
                    # Function-based tool
                    func_name = tool_name.split('.')[-1]
                    if hasattr(mod, func_name):
                        _cached_handler = getattr(mod, func_name)
                    elif hasattr(mod, 'run'):
                        _cached_handler = mod.run
                    else:
                        raise AttributeError(f"Module {module_path} has no {func_name} or run function")
                        
            except Exception as e:
                logger.error(f"Failed to load tool {tool_name}: {e}")
                raise RuntimeError(f"Tool {tool_name} failed to load: {e}")
        
        return _cached_handler(**kwargs)
    
    return lazy_handler


def _infer_tool_hints(tool_name: str) -> Dict[str, bool]:
    """
    Infer tool annotation hints from tool name/category.
    
    Args:
        tool_name: Full tool name (e.g., "praisonai.memory.show")
        
    Returns:
        Dict with readOnlyHint, destructiveHint, idempotentHint, openWorldHint
    """
    name_lower = tool_name.lower()
    
    # Default hints per MCP 2025-11-25 spec
    hints = {
        "read_only_hint": False,
        "destructive_hint": True,
        "idempotent_hint": False,
        "open_world_hint": True,
    }
    
    # Read-only patterns
    read_only_patterns = ['show', 'list', 'get', 'read', 'search', 'find', 'query', 'info', 'status']
    for pattern in read_only_patterns:
        if pattern in name_lower:
            hints["read_only_hint"] = True
            hints["destructive_hint"] = False
            break
    
    # Idempotent patterns
    idempotent_patterns = ['set', 'update', 'configure']
    for pattern in idempotent_patterns:
        if pattern in name_lower:
            hints["idempotent_hint"] = True
            break
    
    # Closed-world patterns (internal tools)
    closed_world_patterns = ['memory', 'session', 'config', 'local']
    for pattern in closed_world_patterns:
        if pattern in name_lower:
            hints["open_world_hint"] = False
            break
    
    return hints


def _extract_category(tool_name: str) -> Optional[str]:
    """Extract category from tool name."""
    parts = tool_name.split('.')
    if len(parts) >= 2:
        return parts[-2]  # e.g., "praisonai.memory.show" -> "memory"
    return None


def register_praisonai_tools(
    namespace_prefix: str = "praisonai.agents.",
    skip_on_collision: bool = True,
) -> int:
    """
    Bridge praisonaiagents tools to MCP registry.
    
    Args:
        namespace_prefix: Prefix to add to tool names to avoid collisions
        skip_on_collision: If True, skip tools that already exist; if False, raise error
        
    Returns:
        Number of tools registered
    """
    global _bridge_enabled
    
    if not is_bridge_available():
        logger.debug("praisonaiagents.tools not available, skipping bridge")
        return 0
    
    from ..registry import get_tool_registry, MCPToolDefinition
    
    registry = get_tool_registry()
    tool_mappings = get_tool_mappings()
    
    registered_count = 0
    
    for tool_name, mapping_info in tool_mappings.items():
        # Handle different mapping formats
        if isinstance(mapping_info, tuple):
            if len(mapping_info) >= 2:
                module_path, class_name = mapping_info[0], mapping_info[1]
            else:
                module_path, class_name = mapping_info[0], None
        elif isinstance(mapping_info, str):
            module_path, class_name = mapping_info, None
        else:
            logger.warning(f"Unknown mapping format for {tool_name}: {type(mapping_info)}")
            continue
        
        # Create namespaced name
        full_name = f"{namespace_prefix}{tool_name}"
        
        # Check for collision
        if full_name in _registered_tools:
            if skip_on_collision:
                logger.debug(f"Skipping duplicate tool: {full_name}")
                continue
            else:
                raise ValueError(f"Tool name collision: {full_name}")
        
        # Check if already in registry
        existing = registry.get(full_name)
        if existing is not None:
            if skip_on_collision:
                logger.debug(f"Tool already registered: {full_name}")
                continue
            else:
                raise ValueError(f"Tool already in registry: {full_name}")
        
        try:
            # Create lazy handler
            handler = _create_lazy_handler(module_path, class_name, tool_name)
            
            # Infer hints
            hints = _infer_tool_hints(tool_name)
            category = _extract_category(tool_name)
            
            # Create tool definition
            tool_def = MCPToolDefinition(
                name=full_name,
                description=f"PraisonAI Agents tool: {tool_name}",
                handler=handler,
                input_schema={"type": "object", "properties": {}},  # Will be refined on first call
                category=category,
                **hints,
            )
            
            # Register directly to avoid re-processing
            registry._tools[full_name] = tool_def
            _registered_tools.add(full_name)
            registered_count += 1
            
            logger.debug(f"Registered bridged tool: {full_name}")
            
        except Exception as e:
            logger.warning(f"Failed to register tool {tool_name}: {e}")
            continue
    
    _bridge_enabled = True
    logger.info(f"Registry bridge registered {registered_count} tools from praisonaiagents")
    
    return registered_count


def unregister_bridged_tools() -> int:
    """
    Remove all bridged tools from the registry.
    
    Returns:
        Number of tools removed
    """
    global _bridge_enabled
    
    from ..registry import get_tool_registry
    
    registry = get_tool_registry()
    removed_count = 0
    
    for tool_name in list(_registered_tools):
        if tool_name in registry._tools:
            del registry._tools[tool_name]
            removed_count += 1
    
    _registered_tools.clear()
    _bridge_enabled = False
    
    logger.info(f"Removed {removed_count} bridged tools")
    return removed_count


def is_bridge_enabled() -> bool:
    """Check if the bridge is currently enabled."""
    return _bridge_enabled


def get_bridged_tool_count() -> int:
    """Get the number of bridged tools."""
    return len(_registered_tools)


def list_bridged_tools() -> List[str]:
    """List all bridged tool names."""
    return list(_registered_tools)
