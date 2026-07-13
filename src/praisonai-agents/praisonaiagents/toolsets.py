"""Named toolset groups for organizing tools into reusable collections.

This module provides functionality to define named groups of tools that can be
enabled or disabled as a unit, supporting composition via includes and 
scenario-specific agent deployments.

Usage:
    from praisonaiagents import toolsets
    
    # Define toolsets
    toolsets.register_toolset("web", tools=["internet_search", "crawl4ai"])
    toolsets.register_toolset("files", tools=["read_file", "write_file"])
    toolsets.register_toolset("research", includes=["web", "files"])
    
    # Use in agent
    agent = Agent(role="researcher", toolsets=["research"])
"""

import logging
import threading
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set

logger = logging.getLogger(__name__)


@dataclass
class ToolsetSpec:
    """Specification for a named toolset group.
    
    Attributes:
        name: Unique name for the toolset
        tools: List of tool names included directly in this toolset
        includes: List of other toolset names to include (recursive composition)
        description: Optional description of the toolset's purpose
    """
    name: str
    tools: List[str] = field(default_factory=list)
    includes: List[str] = field(default_factory=list)
    description: str = ""


class ToolsetRegistry:
    """Registry for managing named toolset groups.
    
    Provides thread-safe registration and resolution of toolset groups,
    with support for recursive composition via includes.
    """
    
    def __init__(self):
        self._toolsets: Dict[str, ToolsetSpec] = {}
        self._lock = threading.RLock()  # Thread-safe for multi-agent scenarios
        self._prebuilt_loaded = False
    
    def register_toolset(
        self,
        name: str,
        tools: Optional[List[str]] = None,
        includes: Optional[List[str]] = None,
        description: str = "",
        overwrite: bool = False
    ) -> None:
        """Register a named toolset.
        
        Args:
            name: Unique name for the toolset
            tools: List of tool names to include directly
            includes: List of other toolset names to include
            description: Optional description
            overwrite: If True, overwrite existing toolset with same name
            
        Raises:
            ValueError: If toolset already exists and overwrite=False
        """
        with self._lock:
            if name in self._toolsets and not overwrite:
                logger.debug(f"Toolset '{name}' already registered, skipping")
                return
                
            toolset = ToolsetSpec(
                name=name,
                tools=list(tools) if tools else [],
                includes=list(includes) if includes else [],
                description=description
            )
            self._toolsets[name] = toolset
            logger.debug(f"Registered toolset: {name}")
    
    def unregister_toolset(self, name: str) -> bool:
        """Remove a toolset from the registry.
        
        Args:
            name: Toolset name to remove
            
        Returns:
            True if toolset was removed, False if not found
        """
        with self._lock:
            if name in self._toolsets:
                del self._toolsets[name]
                logger.debug(f"Unregistered toolset: {name}")
                return True
            return False
    
    def get_toolset(self, name: str) -> Optional[ToolsetSpec]:
        """Get a toolset by name.
        
        Args:
            name: Toolset name
            
        Returns:
            ToolsetSpec or None if not found
        """
        with self._lock:
            self._ensure_prebuilt_loaded()
            spec = self._toolsets.get(name)
            if spec is None:
                return None
            # Return defensive copy to prevent external mutation
            return ToolsetSpec(
                name=spec.name,
                tools=list(spec.tools),
                includes=list(spec.includes),
                description=spec.description,
            )
    
    def list_toolsets(self) -> List[str]:
        """List all registered toolset names."""
        with self._lock:
            self._ensure_prebuilt_loaded()
            return list(self._toolsets.keys())
    
    def resolve_toolset(self, name: str) -> List[str]:
        """Resolve a toolset name to a flat list of tool names.
        
        Recursively expands includes to produce the final list of tools.
        Handles circular dependencies by tracking visited toolsets.
        
        Args:
            name: Toolset name to resolve
            
        Returns:
            List of unique tool names
            
        Raises:
            ValueError: If toolset not found or circular dependency detected
        """
        with self._lock:
            self._ensure_prebuilt_loaded()
            tools = self._resolve_toolset_recursive(name, set())
            # Ensure uniqueness while preserving order
            seen = set()
            unique_tools = []
            for tool in tools:
                if tool not in seen:
                    seen.add(tool)
                    unique_tools.append(tool)
            return unique_tools
    
    def resolve_toolset_for_model(
        self, name: str, model: Optional[str] = None
    ) -> List[str]:
        """Resolve a toolset, honouring the model-family preferred edit format.

        Behaves exactly like :meth:`resolve_toolset` but, when the resolved
        harness profile expresses a preferred edit primitive (e.g.
        ``apply_patch`` vs ``edit_file``) and both primitives are present, the
        preferred one is advertised first. Both remain available, so unknown
        models (default profile) reproduce the current ordering byte-for-byte.

        Args:
            name: Toolset name to resolve.
            model: Active model id used to resolve the harness profile.

        Returns:
            List of unique tool names, edit primitives ordered by preference.
        """
        tools = self.resolve_toolset(name)
        if not model:
            return tools
        return self._apply_preferred_edit_order(tools, model)

    @staticmethod
    def _apply_preferred_edit_order(tools: List[str], model: str) -> List[str]:
        """Reorder edit primitives so the model's preferred one is advertised first.

        Resolves the harness profile for ``model`` and, when it expresses a
        preferred edit primitive present alongside another edit primitive,
        moves the preferred one ahead while preserving every other tool's
        position. Never raises; any resolution error leaves ``tools`` unchanged
        (behaviour-preserving default).
        """
        try:
            from .model_harness import resolve_harness
            preferred = resolve_harness(model).preferred_edit_format
        except Exception:
            preferred = None
        if not preferred or preferred not in tools:
            return tools
        edit_primitives = {"edit_file", "apply_patch"}
        if not any(t in edit_primitives and t != preferred for t in tools):
            return tools
        reordered = []
        inserted = False
        for tool in tools:
            if tool in edit_primitives:
                if not inserted:
                    reordered.append(preferred)
                    reordered.extend(
                        t for t in tools if t in edit_primitives and t != preferred
                    )
                    inserted = True
                # skip other edit primitives; already added
                continue
            reordered.append(tool)
        return reordered

    def resolve_toolsets(self, names: List[str]) -> List[str]:
        """Resolve multiple toolset names to a flat list of tool names.
        
        Args:
            names: List of toolset names to resolve
            
        Returns:
            List of unique tool names from all toolsets
        """
        with self._lock:
            all_tools = []
            for name in names:
                tools = self.resolve_toolset(name)
                all_tools.extend(tools)
            # Return unique tools while preserving order
            seen = set()
            unique_tools = []
            for tool in all_tools:
                if tool not in seen:
                    seen.add(tool)
                    unique_tools.append(tool)
            return unique_tools

    def resolve_toolsets_for_model(
        self, names: List[str], model: Optional[str] = None
    ) -> List[str]:
        """Resolve multiple toolsets, honouring the model's preferred edit format.

        Identical to :meth:`resolve_toolsets` but, when ``model`` resolves to a
        harness profile expressing a preferred edit primitive and both edit
        primitives are present, the preferred one is advertised first. Falsy or
        unknown models reproduce :meth:`resolve_toolsets` byte-for-byte.

        Args:
            names: List of toolset names to resolve.
            model: Active model id used to resolve the harness profile.

        Returns:
            List of unique tool names, edit primitives ordered by preference.
        """
        tools = self.resolve_toolsets(names)
        if not model:
            return tools
        return self._apply_preferred_edit_order(tools, model)
    
    def _resolve_toolset_recursive(self, name: str, visited: Set[str]) -> List[str]:
        """Recursive helper for toolset resolution with cycle detection."""
        if name in visited:
            raise ValueError(f"Circular dependency detected in toolset: {name}")
        
        toolset = self._toolsets.get(name)
        if toolset is None:
            raise ValueError(f"Toolset not found: {name}")
        
        visited.add(name)
        
        # Collect tools from this toolset
        all_tools = list(toolset.tools)
        
        # Recursively resolve included toolsets
        for include_name in toolset.includes:
            included_tools = self._resolve_toolset_recursive(include_name, visited.copy())
            all_tools.extend(included_tools)
        
        return all_tools
    
    def _ensure_prebuilt_loaded(self):
        """Ensure prebuilt toolsets are loaded exactly once."""
        if not self._prebuilt_loaded:
            self._load_prebuilt_toolsets()
            self._prebuilt_loaded = True
    
    def _load_prebuilt_toolsets(self):
        """Load standard prebuilt toolsets that ship with PraisonAI."""
        # Web-related tools
        self.register_toolset(
            "web",
            tools=["internet_search", "duckduckgo", "searxng_search", "tavily_search", "exa_search"],
            description="Web search and crawling tools"
        )
        
        # File system tools
        self.register_toolset(
            "files", 
            tools=["read_file", "write_file", "list_files", "get_file_info", "copy_file", "move_file", "delete_file"],
            description="File system operations"
        )
        
        # Code execution tools
        self.register_toolset(
            "code",
            tools=["execute_code", "analyze_code", "format_code", "lint_code"],
            description="Python code execution and analysis"
        )
        
        # System administration tools
        self.register_toolset(
            "system",
            tools=["execute_command", "list_processes", "kill_process", "get_system_info"],
            description="System administration and shell operations"
        )
        
        # Web scraping/crawling tools
        self.register_toolset(
            "scraping",
            tools=["scrape_page", "extract_links", "crawl", "extract_text"],
            description="Web page scraping and content extraction"
        )
        
        # Research workflow (composition example)
        self.register_toolset(
            "research",
            tools=[],  # No direct tools, only composed ones
            includes=["web", "files", "scraping"],
            description="Complete research workflow with web search, file ops, and scraping"
        )
        
        # Safe toolset for restricted environments
        self.register_toolset(
            "safe",
            tools=["internet_search", "read_file", "tavily_search"],
            description="Minimal safe toolset for restricted environments"
        )
        
        # Development workflow
        self.register_toolset(
            "development",
            tools=[],
            includes=["code", "files", "system"],
            description="Complete development workflow with code execution, files, and system access"
        )

        # Coding workflow (prefers diff-based edit_file/apply_patch over blunt write_file)
        self.register_toolset(
            "coding",
            tools=[
                "read_file", "edit_file", "apply_patch",
                "grep", "glob", "execute_command",
                "todo_add", "todo_list", "todo_update",
            ],
            description="Coding workflow with diff-based edits (edit_file for existing files, apply_patch to create new files), code search, and shell execution"
        )

        logger.debug("Loaded prebuilt toolsets: web, files, code, system, scraping, research, safe, development, coding")
    
    def clear(self) -> None:
        """Clear all registered toolsets."""
        with self._lock:
            self._toolsets.clear()
            self._prebuilt_loaded = False
    
    def __contains__(self, name: str) -> bool:
        with self._lock:
            self._ensure_prebuilt_loaded()
            return name in self._toolsets
    
    def __len__(self) -> int:
        with self._lock:
            self._ensure_prebuilt_loaded()
            return len(self._toolsets)
    
    def __repr__(self) -> str:
        with self._lock:
            self._ensure_prebuilt_loaded()
            return f"ToolsetRegistry(toolsets={len(self._toolsets)})"


# Global registry instance (protected by _registry_lock for thread safety)
_registry_lock = threading.Lock()
_global_registry: Optional[ToolsetRegistry] = None


def get_toolset_registry() -> ToolsetRegistry:
    """Get the global toolset registry instance. Thread-safe singleton."""
    global _global_registry
    if _global_registry is None:
        with _registry_lock:
            # Double-checked locking pattern
            if _global_registry is None:
                _global_registry = ToolsetRegistry()
    return _global_registry


def register_toolset(
    name: str,
    tools: Optional[List[str]] = None,
    includes: Optional[List[str]] = None,
    description: str = "",
    overwrite: bool = False
) -> None:
    """Register a named toolset with the global registry.
    
    Args:
        name: Unique name for the toolset
        tools: List of tool names to include directly
        includes: List of other toolset names to include
        description: Optional description
        overwrite: If True, overwrite existing toolset
    """
    get_toolset_registry().register_toolset(name, tools, includes, description, overwrite)


def resolve_toolset(name: str) -> List[str]:
    """Resolve a toolset name to a flat list of tool names.
    
    Args:
        name: Toolset name to resolve
        
    Returns:
        List of unique tool names
    """
    return get_toolset_registry().resolve_toolset(name)


def resolve_toolsets(names: List[str]) -> List[str]:
    """Resolve multiple toolset names to a flat list of tool names.
    
    Args:
        names: List of toolset names to resolve
        
    Returns:
        List of unique tool names from all toolsets
    """
    return get_toolset_registry().resolve_toolsets(names)


def resolve_toolsets_for_model(
    names: List[str], model: Optional[str] = None
) -> List[str]:
    """Resolve multiple toolsets, honouring the model's preferred edit format.

    Falsy / unknown models reproduce :func:`resolve_toolsets` byte-for-byte.

    Args:
        names: List of toolset names to resolve.
        model: Active model id used to resolve the harness profile.

    Returns:
        List of unique tool names, edit primitives ordered by preference.
    """
    return get_toolset_registry().resolve_toolsets_for_model(names, model)


def list_toolsets() -> List[str]:
    """List all registered toolset names."""
    return get_toolset_registry().list_toolsets()


def get_toolset(name: str) -> Optional[ToolsetSpec]:
    """Get a toolset by name."""
    return get_toolset_registry().get_toolset(name)


def unregister_toolset(name: str) -> bool:
    """Remove a toolset from the global registry.
    
    Args:
        name: Toolset name to remove
        
    Returns:
        True if removed, False if not found
    """
    return get_toolset_registry().unregister_toolset(name)


def has_toolset(name: str) -> bool:
    """Check if a toolset is registered.
    
    Args:
        name: Toolset name to check
        
    Returns:
        True if toolset exists, False otherwise
    """
    return name in get_toolset_registry()