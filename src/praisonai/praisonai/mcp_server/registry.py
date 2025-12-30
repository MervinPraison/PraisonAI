"""
MCP Tool/Resource/Prompt Registry

Provides a centralized registry for MCP tools, resources, and prompts.
Supports lazy registration, schema generation, pagination, and search.

MCP Protocol Version: 2025-11-25
"""

import base64
import inspect
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

logger = logging.getLogger(__name__)


# Default page size for pagination
DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 100


def encode_cursor(offset: int, snapshot_hash: Optional[str] = None) -> str:
    """Encode pagination cursor as base64url."""
    data = f"{offset}"
    if snapshot_hash:
        data = f"{offset}:{snapshot_hash}"
    return base64.urlsafe_b64encode(data.encode()).decode().rstrip("=")


def decode_cursor(cursor: str) -> Tuple[int, Optional[str]]:
    """
    Decode pagination cursor from base64url.
    
    Returns:
        Tuple of (offset, snapshot_hash)
        
    Raises:
        ValueError: If cursor is invalid
    """
    try:
        # Add padding if needed
        padding = 4 - len(cursor) % 4
        if padding != 4:
            cursor += "=" * padding
        data = base64.urlsafe_b64decode(cursor).decode()
        if ":" in data:
            parts = data.split(":", 1)
            return int(parts[0]), parts[1]
        return int(data), None
    except Exception as e:
        raise ValueError(f"Invalid cursor: {e}")


@dataclass
class MCPToolDefinition:
    """Definition of an MCP tool with MCP 2025-11-25 annotations."""
    name: str
    description: str
    handler: Callable
    input_schema: Dict[str, Any]
    output_schema: Optional[Dict[str, Any]] = None
    annotations: Optional[Dict[str, Any]] = None
    # MCP 2025-11-25 tool annotation hints
    title: Optional[str] = None
    category: Optional[str] = None
    tags: Optional[List[str]] = None
    # Behavior hints per MCP 2025-11-25 spec
    read_only_hint: bool = False
    destructive_hint: bool = True
    idempotent_hint: bool = False
    open_world_hint: bool = True
    
    def to_mcp_schema(self) -> Dict[str, Any]:
        """Convert to MCP tool schema format per MCP 2025-11-25 spec."""
        schema = {
            "name": self.name,
            "description": self.description,
            "inputSchema": self.input_schema,
        }
        if self.output_schema:
            schema["outputSchema"] = self.output_schema
        
        # Build annotations per MCP 2025-11-25 spec
        annotations = self.annotations.copy() if self.annotations else {}
        
        # Add behavior hints
        annotations["readOnlyHint"] = self.read_only_hint
        annotations["destructiveHint"] = self.destructive_hint
        annotations["idempotentHint"] = self.idempotent_hint
        annotations["openWorldHint"] = self.open_world_hint
        
        # Add title if present
        if self.title:
            annotations["title"] = self.title
        
        schema["annotations"] = annotations
        return schema


@dataclass
class MCPResourceDefinition:
    """Definition of an MCP resource."""
    uri: str
    name: str
    description: str
    handler: Callable
    mime_type: str = "application/json"
    
    def to_mcp_schema(self) -> Dict[str, Any]:
        """Convert to MCP resource schema format."""
        return {
            "uri": self.uri,
            "name": self.name,
            "description": self.description,
            "mimeType": self.mime_type,
        }


@dataclass
class MCPPromptDefinition:
    """Definition of an MCP prompt."""
    name: str
    description: str
    handler: Callable
    arguments: List[Dict[str, Any]] = field(default_factory=list)
    
    def to_mcp_schema(self) -> Dict[str, Any]:
        """Convert to MCP prompt schema format."""
        return {
            "name": self.name,
            "description": self.description,
            "arguments": self.arguments,
        }


class MCPToolRegistry:
    """Registry for MCP tools."""
    
    def __init__(self):
        self._tools: Dict[str, MCPToolDefinition] = {}
        self._lazy_loaders: List[Callable[[], None]] = []
    
    def register(
        self,
        name: str,
        handler: Callable,
        description: Optional[str] = None,
        input_schema: Optional[Dict[str, Any]] = None,
        output_schema: Optional[Dict[str, Any]] = None,
        annotations: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Register a tool."""
        if description is None:
            description = inspect.getdoc(handler) or f"Tool: {name}"
            if "\n" in description:
                description = description.split("\n")[0]
        
        if input_schema is None:
            input_schema = self._generate_input_schema(handler)
        
        self._tools[name] = MCPToolDefinition(
            name=name,
            description=description,
            handler=handler,
            input_schema=input_schema,
            output_schema=output_schema,
            annotations=annotations,
        )
        logger.debug(f"Registered MCP tool: {name}")
    
    def register_lazy(self, loader: Callable[[], None]) -> None:
        """Register a lazy loader that will be called before listing tools."""
        self._lazy_loaders.append(loader)
    
    def _ensure_loaded(self) -> None:
        """Ensure all lazy loaders have been called."""
        for loader in self._lazy_loaders:
            try:
                loader()
            except Exception as e:
                logger.warning(f"Lazy loader failed: {e}")
        self._lazy_loaders.clear()
    
    def get(self, name: str) -> Optional[MCPToolDefinition]:
        """Get a tool by name."""
        self._ensure_loaded()
        return self._tools.get(name)
    
    def list_all(self) -> List[MCPToolDefinition]:
        """List all registered tools."""
        self._ensure_loaded()
        return list(self._tools.values())
    
    def list_schemas(self) -> List[Dict[str, Any]]:
        """List all tool schemas."""
        return [tool.to_mcp_schema() for tool in self.list_all()]
    
    def list_paginated(
        self,
        cursor: Optional[str] = None,
        page_size: int = DEFAULT_PAGE_SIZE,
    ) -> Tuple[List[Dict[str, Any]], Optional[str]]:
        """
        List tool schemas with pagination per MCP 2025-11-25 spec.
        
        Args:
            cursor: Opaque cursor from previous response
            page_size: Number of items per page (server-determined, max 100)
            
        Returns:
            Tuple of (tools list, nextCursor or None if no more results)
            
        Raises:
            ValueError: If cursor is invalid
        """
        all_tools = self.list_all()
        total = len(all_tools)
        
        # Decode cursor to get offset
        offset = 0
        if cursor:
            offset, _ = decode_cursor(cursor)
            if offset < 0 or offset >= total:
                raise ValueError(f"Invalid cursor: offset {offset} out of range")
        
        # Clamp page size
        page_size = min(page_size, MAX_PAGE_SIZE)
        
        # Get page
        end = min(offset + page_size, total)
        page = all_tools[offset:end]
        schemas = [tool.to_mcp_schema() for tool in page]
        
        # Generate next cursor if more results
        next_cursor = None
        if end < total:
            next_cursor = encode_cursor(end)
        
        return schemas, next_cursor
    
    def search(
        self,
        query: Optional[str] = None,
        category: Optional[str] = None,
        tags: Optional[List[str]] = None,
        read_only: Optional[bool] = None,
        cursor: Optional[str] = None,
        page_size: int = DEFAULT_PAGE_SIZE,
    ) -> Tuple[List[Dict[str, Any]], Optional[str], int]:
        """
        Search tools with filtering and pagination.
        
        Args:
            query: Text to search in name, description, tags
            category: Filter by category
            tags: Filter by tags (any match)
            read_only: Filter by readOnlyHint
            cursor: Pagination cursor
            page_size: Items per page
            
        Returns:
            Tuple of (tools list, nextCursor, total_count)
        """
        all_tools = self.list_all()
        
        # Apply filters
        filtered = []
        query_lower = query.lower() if query else None
        
        for tool in all_tools:
            # Query filter
            if query_lower:
                searchable = f"{tool.name} {tool.description}".lower()
                if tool.tags:
                    searchable += " " + " ".join(tool.tags).lower()
                if tool.category:
                    searchable += " " + tool.category.lower()
                if query_lower not in searchable:
                    continue
            
            # Category filter
            if category and tool.category != category:
                continue
            
            # Tags filter (any match)
            if tags:
                tool_tags = set(tool.tags or [])
                if not tool_tags.intersection(set(tags)):
                    continue
            
            # Read-only filter
            if read_only is not None and tool.read_only_hint != read_only:
                continue
            
            filtered.append(tool)
        
        total = len(filtered)
        
        # Pagination
        offset = 0
        if cursor:
            offset, _ = decode_cursor(cursor)
            if offset < 0:
                offset = 0
        
        page_size = min(page_size, MAX_PAGE_SIZE)
        end = min(offset + page_size, total)
        page = filtered[offset:end]
        schemas = [tool.to_mcp_schema() for tool in page]
        
        # Next cursor
        next_cursor = None
        if end < total:
            next_cursor = encode_cursor(end)
        
        return schemas, next_cursor, total
    
    def _generate_input_schema(self, handler: Callable) -> Dict[str, Any]:
        """Generate JSON schema from function signature."""
        sig = inspect.signature(handler)
        hints = getattr(handler, "__annotations__", {})
        
        properties = {}
        required = []
        
        for param_name, param in sig.parameters.items():
            if param_name in ("self", "cls"):
                continue
            
            prop = {"type": "string"}  # Default
            
            # Get type hint
            hint = hints.get(param_name)
            if hint:
                prop = self._type_to_json_schema(hint)
            
            # Get description from docstring if available
            docstring = inspect.getdoc(handler)
            if docstring:
                # Try to extract param description from docstring
                for line in docstring.split("\n"):
                    if f":param {param_name}:" in line:
                        # Extract description after the param marker
                        parts = line.split(f":param {param_name}:", 1)
                        if len(parts) > 1:
                            prop["description"] = parts[1].strip()
            
            properties[param_name] = prop
            
            if param.default is inspect.Parameter.empty:
                required.append(param_name)
        
        return {
            "type": "object",
            "properties": properties,
            "required": required if required else None,
        }
    
    def _type_to_json_schema(self, hint: Any) -> Dict[str, Any]:
        """Convert Python type hint to JSON schema."""
        if hint is str:
            return {"type": "string"}
        elif hint is int:
            return {"type": "integer"}
        elif hint is float:
            return {"type": "number"}
        elif hint is bool:
            return {"type": "boolean"}
        elif hint is list or (hasattr(hint, "__origin__") and hint.__origin__ is list):
            return {"type": "array", "items": {"type": "string"}}
        elif hint is dict or (hasattr(hint, "__origin__") and hint.__origin__ is dict):
            return {"type": "object"}
        else:
            return {"type": "string"}


class MCPResourceRegistry:
    """Registry for MCP resources."""
    
    def __init__(self):
        self._resources: Dict[str, MCPResourceDefinition] = {}
        self._lazy_loaders: List[Callable[[], None]] = []
    
    def register(
        self,
        uri: str,
        handler: Callable,
        name: Optional[str] = None,
        description: Optional[str] = None,
        mime_type: str = "application/json",
    ) -> None:
        """Register a resource."""
        if name is None:
            name = uri.split("/")[-1] or uri
        if description is None:
            description = inspect.getdoc(handler) or f"Resource: {name}"
            if "\n" in description:
                description = description.split("\n")[0]
        
        self._resources[uri] = MCPResourceDefinition(
            uri=uri,
            name=name,
            description=description,
            handler=handler,
            mime_type=mime_type,
        )
        logger.debug(f"Registered MCP resource: {uri}")
    
    def register_lazy(self, loader: Callable[[], None]) -> None:
        """Register a lazy loader."""
        self._lazy_loaders.append(loader)
    
    def _ensure_loaded(self) -> None:
        """Ensure all lazy loaders have been called."""
        for loader in self._lazy_loaders:
            try:
                loader()
            except Exception as e:
                logger.warning(f"Lazy loader failed: {e}")
        self._lazy_loaders.clear()
    
    def get(self, uri: str) -> Optional[MCPResourceDefinition]:
        """Get a resource by URI."""
        self._ensure_loaded()
        return self._resources.get(uri)
    
    def list_all(self) -> List[MCPResourceDefinition]:
        """List all registered resources."""
        self._ensure_loaded()
        return list(self._resources.values())
    
    def list_schemas(self) -> List[Dict[str, Any]]:
        """List all resource schemas."""
        return [res.to_mcp_schema() for res in self.list_all()]
    
    def list_paginated(
        self,
        cursor: Optional[str] = None,
        page_size: int = DEFAULT_PAGE_SIZE,
    ) -> Tuple[List[Dict[str, Any]], Optional[str]]:
        """
        List resource schemas with pagination per MCP 2025-11-25 spec.
        
        Args:
            cursor: Opaque cursor from previous response
            page_size: Number of items per page
            
        Returns:
            Tuple of (resources list, nextCursor or None)
        """
        all_resources = self.list_all()
        total = len(all_resources)
        
        offset = 0
        if cursor:
            offset, _ = decode_cursor(cursor)
            if offset < 0 or offset >= total:
                raise ValueError(f"Invalid cursor: offset {offset} out of range")
        
        page_size = min(page_size, MAX_PAGE_SIZE)
        end = min(offset + page_size, total)
        page = all_resources[offset:end]
        schemas = [res.to_mcp_schema() for res in page]
        
        next_cursor = None
        if end < total:
            next_cursor = encode_cursor(end)
        
        return schemas, next_cursor


class MCPPromptRegistry:
    """Registry for MCP prompts."""
    
    def __init__(self):
        self._prompts: Dict[str, MCPPromptDefinition] = {}
        self._lazy_loaders: List[Callable[[], None]] = []
    
    def register(
        self,
        name: str,
        handler: Callable,
        description: Optional[str] = None,
        arguments: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        """Register a prompt."""
        if description is None:
            description = inspect.getdoc(handler) or f"Prompt: {name}"
            if "\n" in description:
                description = description.split("\n")[0]
        
        if arguments is None:
            arguments = self._generate_arguments(handler)
        
        self._prompts[name] = MCPPromptDefinition(
            name=name,
            description=description,
            handler=handler,
            arguments=arguments,
        )
        logger.debug(f"Registered MCP prompt: {name}")
    
    def register_lazy(self, loader: Callable[[], None]) -> None:
        """Register a lazy loader."""
        self._lazy_loaders.append(loader)
    
    def _ensure_loaded(self) -> None:
        """Ensure all lazy loaders have been called."""
        for loader in self._lazy_loaders:
            try:
                loader()
            except Exception as e:
                logger.warning(f"Lazy loader failed: {e}")
        self._lazy_loaders.clear()
    
    def get(self, name: str) -> Optional[MCPPromptDefinition]:
        """Get a prompt by name."""
        self._ensure_loaded()
        return self._prompts.get(name)
    
    def list_all(self) -> List[MCPPromptDefinition]:
        """List all registered prompts."""
        self._ensure_loaded()
        return list(self._prompts.values())
    
    def list_schemas(self) -> List[Dict[str, Any]]:
        """List all prompt schemas."""
        return [prompt.to_mcp_schema() for prompt in self.list_all()]
    
    def list_paginated(
        self,
        cursor: Optional[str] = None,
        page_size: int = DEFAULT_PAGE_SIZE,
    ) -> Tuple[List[Dict[str, Any]], Optional[str]]:
        """
        List prompt schemas with pagination per MCP 2025-11-25 spec.
        
        Args:
            cursor: Opaque cursor from previous response
            page_size: Number of items per page
            
        Returns:
            Tuple of (prompts list, nextCursor or None)
        """
        all_prompts = self.list_all()
        total = len(all_prompts)
        
        offset = 0
        if cursor:
            offset, _ = decode_cursor(cursor)
            if offset < 0 or offset >= total:
                raise ValueError(f"Invalid cursor: offset {offset} out of range")
        
        page_size = min(page_size, MAX_PAGE_SIZE)
        end = min(offset + page_size, total)
        page = all_prompts[offset:end]
        schemas = [prompt.to_mcp_schema() for prompt in page]
        
        next_cursor = None
        if end < total:
            next_cursor = encode_cursor(end)
        
        return schemas, next_cursor
    
    def _generate_arguments(self, handler: Callable) -> List[Dict[str, Any]]:
        """Generate prompt arguments from function signature."""
        sig = inspect.signature(handler)
        arguments = []
        
        for param_name, param in sig.parameters.items():
            if param_name in ("self", "cls"):
                continue
            
            arg = {
                "name": param_name,
                "required": param.default is inspect.Parameter.empty,
            }
            
            # Add description if available
            docstring = inspect.getdoc(handler)
            if docstring and f":param {param_name}:" in docstring:
                # Extract description
                pass
            
            arguments.append(arg)
        
        return arguments


# Global registries
_tool_registry = MCPToolRegistry()
_resource_registry = MCPResourceRegistry()
_prompt_registry = MCPPromptRegistry()


def register_tool(
    name: str,
    handler: Optional[Callable] = None,
    description: Optional[str] = None,
    input_schema: Optional[Dict[str, Any]] = None,
    output_schema: Optional[Dict[str, Any]] = None,
    annotations: Optional[Dict[str, Any]] = None,
) -> Union[Callable, None]:
    """
    Register a tool with the global registry.
    
    Can be used as a decorator or called directly.
    
    Example:
        @register_tool("praisonai.memory.show")
        def show_memory(session_id: str = None) -> str:
            '''Show memory contents.'''
            ...
        
        # Or directly:
        register_tool("praisonai.memory.show", show_memory)
    """
    def decorator(fn: Callable) -> Callable:
        _tool_registry.register(
            name=name,
            handler=fn,
            description=description,
            input_schema=input_schema,
            output_schema=output_schema,
            annotations=annotations,
        )
        return fn
    
    if handler is not None:
        decorator(handler)
        return None
    return decorator


def register_resource(
    uri: str,
    handler: Optional[Callable] = None,
    name: Optional[str] = None,
    description: Optional[str] = None,
    mime_type: str = "application/json",
) -> Union[Callable, None]:
    """
    Register a resource with the global registry.
    
    Can be used as a decorator or called directly.
    """
    def decorator(fn: Callable) -> Callable:
        _resource_registry.register(
            uri=uri,
            handler=fn,
            name=name,
            description=description,
            mime_type=mime_type,
        )
        return fn
    
    if handler is not None:
        decorator(handler)
        return None
    return decorator


def register_prompt(
    name: str,
    handler: Optional[Callable] = None,
    description: Optional[str] = None,
    arguments: Optional[List[Dict[str, Any]]] = None,
) -> Union[Callable, None]:
    """
    Register a prompt with the global registry.
    
    Can be used as a decorator or called directly.
    """
    def decorator(fn: Callable) -> Callable:
        _prompt_registry.register(
            name=name,
            handler=fn,
            description=description,
            arguments=arguments,
        )
        return fn
    
    if handler is not None:
        decorator(handler)
        return None
    return decorator


def get_tool_registry() -> MCPToolRegistry:
    """Get the global tool registry."""
    return _tool_registry


def get_resource_registry() -> MCPResourceRegistry:
    """Get the global resource registry."""
    return _resource_registry


def get_prompt_registry() -> MCPPromptRegistry:
    """Get the global prompt registry."""
    return _prompt_registry
