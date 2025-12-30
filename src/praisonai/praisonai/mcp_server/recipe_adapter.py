"""
Recipe MCP Adapter

Adapts PraisonAI recipes to MCP server primitives (tools, resources, prompts).
Enables any recipe to be served as an MCP server.

MCP Protocol Version: 2025-11-25
"""

import asyncio
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, TYPE_CHECKING, Union

if TYPE_CHECKING:
    from .server import MCPServer

from .registry import (
    MCPToolRegistry,
    MCPResourceRegistry,
    MCPPromptRegistry,
)

logger = logging.getLogger(__name__)

# Default denied tools (dangerous by default)
DEFAULT_DENIED_TOOLS: Set[str] = {
    "shell.exec",
    "shell.run",
    "shell_tool",
    "file.write",
    "file.delete",
    "fs.write",
    "fs.delete",
    "network.unrestricted",
    "db.write",
    "db.delete",
    "execute_command",
    "os.system",
    "subprocess.run",
    "eval",
    "exec",
}


@dataclass
class RecipeMCPConfig:
    """Configuration for serving a recipe as MCP server."""
    
    recipe_name: str
    
    # Tool exposure settings
    expose_agent_tools: bool = True
    expose_run_tool: bool = True
    tool_namespace: str = "prefixed"  # "flat", "nested", or "prefixed"
    
    # Resource exposure settings
    expose_config: bool = True
    expose_outputs: bool = True
    
    # Prompt exposure settings
    expose_prompts: bool = True
    expose_agent_instructions: bool = True
    
    # Security settings
    safe_mode: bool = True
    tool_allowlist: Optional[List[str]] = None
    tool_denylist: Optional[List[str]] = None
    workspace_path: Optional[str] = None
    allow_network: bool = False
    env_allowlist: Optional[List[str]] = None
    
    # Server settings
    server_name: Optional[str] = None
    server_version: str = "1.0.0"
    server_description: Optional[str] = None
    server_icon: Optional[str] = None
    
    # Session settings
    session_ttl: int = 3600
    max_concurrent_runs: int = 5
    
    def __post_init__(self):
        if self.server_name is None:
            self.server_name = self.recipe_name
        if self.tool_denylist is None:
            self.tool_denylist = list(DEFAULT_DENIED_TOOLS)


@dataclass
class RecipeToolWrapper:
    """Wrapper for a recipe tool with MCP metadata."""
    
    name: str
    description: str
    handler: Callable
    input_schema: Dict[str, Any]
    output_schema: Optional[Dict[str, Any]] = None
    annotations: Optional[Dict[str, Any]] = None
    icon: Optional[str] = None
    agent_name: Optional[str] = None
    original_name: Optional[str] = None


class RecipeMCPAdapter:
    """
    Adapts a recipe to MCP server primitives.
    
    Maps:
    - Recipe metadata → Server metadata
    - Agent tools → MCP Tools (namespaced)
    - Agent instructions → MCP Prompts
    - Recipe config/outputs → MCP Resources
    
    Example:
        adapter = RecipeMCPAdapter("support-reply")
        adapter.load()
        server = adapter.to_mcp_server()
        server.run(transport="stdio")
    """
    
    def __init__(
        self,
        recipe_name: str,
        config: Optional[RecipeMCPConfig] = None,
    ):
        """
        Initialize recipe adapter.
        
        Args:
            recipe_name: Name of the recipe to adapt
            config: Optional configuration (uses defaults if None)
        """
        self.recipe_name = recipe_name
        self.config = config or RecipeMCPConfig(recipe_name=recipe_name)
        
        self._recipe_config = None
        self._workflow_config = None
        self._loaded = False
        
        # Registries
        self._tool_registry = MCPToolRegistry()
        self._resource_registry = MCPResourceRegistry()
        self._prompt_registry = MCPPromptRegistry()
        
        # Runtime state
        self._active_runs: Dict[str, Any] = {}
        self._run_results: Dict[str, Any] = {}
    
    def load(self) -> None:
        """Load recipe and build MCP registries."""
        if self._loaded:
            return
        
        # Load recipe configuration
        self._recipe_config = self._load_recipe_config()
        if self._recipe_config is None:
            raise ValueError(f"Recipe not found: {self.recipe_name}")
        
        # Load workflow configuration
        self._workflow_config = self._load_workflow_config()
        
        # Build registries
        self._build_tool_registry()
        self._build_resource_registry()
        self._build_prompt_registry()
        
        self._loaded = True
        logger.info(f"Loaded recipe '{self.recipe_name}' as MCP server")
    
    def _load_recipe_config(self) -> Optional[Dict[str, Any]]:
        """Load recipe configuration from template."""
        try:
            from ..recipe.core import _load_recipe
            recipe = _load_recipe(self.recipe_name, offline=False)
            if recipe:
                return recipe.to_dict() if hasattr(recipe, 'to_dict') else recipe.raw
        except ImportError:
            pass
        
        # Fallback: try loading directly from templates
        try:
            from ..templates.discovery import TemplateDiscovery
            discovery = TemplateDiscovery()
            template = discovery.find_template(self.recipe_name)
            if template:
                return self._load_yaml_file(template.path)
        except ImportError:
            pass
        
        return None
    
    def _load_workflow_config(self) -> Optional[Dict[str, Any]]:
        """Load workflow configuration from recipe."""
        if not self._recipe_config:
            return None
        
        # Check for workflow file reference
        workflow_file = self._recipe_config.get("workflow")
        if workflow_file:
            recipe_path = self._recipe_config.get("path")
            if recipe_path:
                workflow_path = Path(recipe_path).parent / workflow_file
                if workflow_path.exists():
                    return self._load_yaml_file(str(workflow_path))
        
        # Check for inline workflow
        if "agents" in self._recipe_config or "tasks" in self._recipe_config:
            return self._recipe_config
        
        return None
    
    def _load_yaml_file(self, path: str) -> Optional[Dict[str, Any]]:
        """Load YAML file."""
        try:
            import yaml
            with open(path, 'r') as f:
                return yaml.safe_load(f)
        except Exception as e:
            logger.warning(f"Failed to load YAML file {path}: {e}")
            return None
    
    def _build_tool_registry(self) -> None:
        """Build tool registry from recipe."""
        # Add recipe.run meta-tool
        if self.config.expose_run_tool:
            self._register_run_tool()
        
        # Add agent tools (if enabled and safe)
        if self.config.expose_agent_tools and self._workflow_config:
            self._register_agent_tools()
    
    def _register_run_tool(self) -> None:
        """Register the recipe.run meta-tool."""
        recipe_name = self.recipe_name
        description = self._recipe_config.get("description", f"Execute the {recipe_name} recipe")
        
        # Build input schema from recipe config_schema
        config_schema = self._recipe_config.get("config_schema", {})
        input_schema = {
            "type": "object",
            "properties": {
                "input": {
                    "type": "object",
                    "description": "Input data for the recipe",
                },
                "config": {
                    "type": "object",
                    "description": "Configuration overrides",
                    "properties": config_schema.get("properties", {}),
                },
                "session_id": {
                    "type": "string",
                    "description": "Optional session ID for state grouping",
                },
            },
            "required": [],
        }
        
        async def run_recipe_handler(
            input: Optional[Dict[str, Any]] = None,
            config: Optional[Dict[str, Any]] = None,
            session_id: Optional[str] = None,
        ) -> Dict[str, Any]:
            """Execute the recipe."""
            return await self._execute_recipe(input, config, session_id)
        
        tool_name = self._namespace_tool(recipe_name, None, "run")
        
        self._tool_registry.register(
            name=tool_name,
            handler=run_recipe_handler,
            description=description,
            input_schema=input_schema,
            annotations={
                "recipe": recipe_name,
                "type": "recipe_run",
            },
        )
    
    def _register_agent_tools(self) -> None:
        """Register individual agent tools."""
        agents = self._workflow_config.get("agents", [])
        
        for agent_config in agents:
            agent_name = agent_config.get("name", "agent")
            agent_tools = agent_config.get("tools", [])
            
            for tool_spec in agent_tools:
                tool_name = tool_spec if isinstance(tool_spec, str) else tool_spec.get("name", "")
                
                # Check if tool is allowed
                if not self._is_tool_allowed(tool_name):
                    logger.debug(f"Skipping denied tool: {tool_name}")
                    continue
                
                # Create wrapper for the tool
                self._register_agent_tool(agent_name, tool_name, tool_spec)
    
    def _register_agent_tool(
        self,
        agent_name: str,
        tool_name: str,
        tool_spec: Union[str, Dict[str, Any]],
    ) -> None:
        """Register a single agent tool."""
        # Get tool description
        if isinstance(tool_spec, dict):
            description = tool_spec.get("description", f"Tool: {tool_name}")
            input_schema = tool_spec.get("input_schema", {"type": "object", "properties": {}})
        else:
            description = f"Tool: {tool_name}"
            input_schema = {"type": "object", "properties": {}}
        
        # Create namespaced tool name
        namespaced_name = self._namespace_tool(self.recipe_name, agent_name, tool_name)
        
        async def tool_handler(**kwargs) -> Dict[str, Any]:
            """Execute the agent tool."""
            return await self._execute_agent_tool(agent_name, tool_name, kwargs)
        
        self._tool_registry.register(
            name=namespaced_name,
            handler=tool_handler,
            description=description,
            input_schema=input_schema,
            annotations={
                "recipe": self.recipe_name,
                "agent": agent_name,
                "original_tool": tool_name,
                "type": "agent_tool",
            },
        )
    
    def _is_tool_allowed(self, tool_name: str) -> bool:
        """Check if a tool is allowed based on config."""
        if not self.config.safe_mode:
            return True
        
        # Check explicit allowlist
        if self.config.tool_allowlist:
            return tool_name in self.config.tool_allowlist
        
        # Check denylist
        if self.config.tool_denylist:
            for denied in self.config.tool_denylist:
                if denied in tool_name or tool_name in denied:
                    return False
        
        return True
    
    def _namespace_tool(
        self,
        recipe_name: str,
        agent_name: Optional[str],
        tool_name: str,
    ) -> str:
        """Generate namespaced tool name per MCP 2025-11-25 guidance."""
        # Sanitize names
        recipe = self._sanitize_name(recipe_name)
        tool = self._sanitize_name(tool_name)
        
        if self.config.tool_namespace == "flat":
            return tool
        elif self.config.tool_namespace == "nested":
            if agent_name:
                agent = self._sanitize_name(agent_name)
                return f"{recipe}/{agent}/{tool}"
            return f"{recipe}/{tool}"
        else:  # prefixed (default)
            if agent_name:
                agent = self._sanitize_name(agent_name)
                return f"{recipe}.{agent}.{tool}"
            return f"{recipe}.{tool}"
    
    def _sanitize_name(self, name: str) -> str:
        """Sanitize name for MCP tool naming."""
        # Convert to lowercase, replace spaces/underscores with hyphens
        name = name.lower().strip()
        name = re.sub(r'[_\s]+', '-', name)
        name = re.sub(r'[^a-z0-9\-]', '', name)
        return name
    
    def _build_resource_registry(self) -> None:
        """Build resource registry from recipe."""
        if not self._recipe_config:
            return
        
        recipe_name = self.recipe_name
        
        # Register config resource
        if self.config.expose_config:
            self._resource_registry.register(
                uri=f"recipe://{recipe_name}/config",
                handler=lambda: self._recipe_config,
                name=f"{recipe_name}-config",
                description=f"Configuration for {recipe_name} recipe",
                mime_type="application/json",
            )
        
        # Register schema resource
        config_schema = self._recipe_config.get("config_schema")
        if config_schema:
            self._resource_registry.register(
                uri=f"recipe://{recipe_name}/schema",
                handler=lambda: config_schema,
                name=f"{recipe_name}-schema",
                description=f"Input schema for {recipe_name} recipe",
                mime_type="application/json",
            )
        
        # Register outputs resource
        if self.config.expose_outputs:
            outputs = self._recipe_config.get("outputs", [])
            if outputs:
                self._resource_registry.register(
                    uri=f"recipe://{recipe_name}/outputs",
                    handler=lambda: outputs,
                    name=f"{recipe_name}-outputs",
                    description=f"Output definitions for {recipe_name} recipe",
                    mime_type="application/json",
                )
    
    def _build_prompt_registry(self) -> None:
        """Build prompt registry from recipe."""
        if not self.config.expose_prompts:
            return
        
        recipe_name = self.recipe_name
        
        # Register recipe description as prompt
        description = self._recipe_config.get("description", "")
        if description:
            self._prompt_registry.register(
                name=f"{recipe_name}-description",
                handler=lambda: description,
                description=f"Description of {recipe_name} recipe",
            )
        
        # Register agent instructions as prompts
        if self.config.expose_agent_instructions and self._workflow_config:
            agents = self._workflow_config.get("agents", [])
            for agent_config in agents:
                agent_name = agent_config.get("name", "agent")
                instructions = agent_config.get("instructions", agent_config.get("role", ""))
                
                if instructions:
                    self._prompt_registry.register(
                        name=f"{recipe_name}-{self._sanitize_name(agent_name)}-instructions",
                        handler=lambda inst=instructions: inst,
                        description=f"Instructions for {agent_name} agent in {recipe_name}",
                    )
    
    async def _execute_recipe(
        self,
        input: Optional[Dict[str, Any]] = None,
        config: Optional[Dict[str, Any]] = None,
        session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Execute the recipe."""
        try:
            from ..recipe.core import run as recipe_run
            
            result = recipe_run(
                name=self.recipe_name,
                input=input or {},
                config=config,
                session_id=session_id,
            )
            
            return result.to_dict() if hasattr(result, 'to_dict') else {"output": result}
            
        except ImportError:
            return {"error": "Recipe execution not available", "status": "failed"}
        except Exception as e:
            logger.exception(f"Recipe execution failed: {e}")
            return {"error": str(e), "status": "failed"}
    
    async def _execute_agent_tool(
        self,
        agent_name: str,
        tool_name: str,
        arguments: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Execute an agent tool directly."""
        try:
            # Try to load and execute the tool
            from praisonaiagents.tools import get_tool
            
            tool = get_tool(tool_name)
            if tool:
                if asyncio.iscoroutinefunction(tool):
                    result = await tool(**arguments)
                else:
                    result = tool(**arguments)
                return {"result": result, "status": "success"}
            
            return {"error": f"Tool not found: {tool_name}", "status": "failed"}
            
        except ImportError:
            return {"error": "Tool execution not available", "status": "failed"}
        except Exception as e:
            logger.exception(f"Tool execution failed: {e}")
            return {"error": str(e), "status": "failed"}
    
    def to_mcp_server(self) -> "MCPServer":
        """Create MCPServer instance from this adapter."""
        if not self._loaded:
            self.load()
        
        from .server import MCPServer
        
        return MCPServer(
            name=self.config.server_name or self.recipe_name,
            version=self.config.server_version,
            tool_registry=self._tool_registry,
            resource_registry=self._resource_registry,
            prompt_registry=self._prompt_registry,
            instructions=self._recipe_config.get("description", ""),
        )
    
    def get_tool_registry(self) -> MCPToolRegistry:
        """Get the tool registry."""
        return self._tool_registry
    
    def get_resource_registry(self) -> MCPResourceRegistry:
        """Get the resource registry."""
        return self._resource_registry
    
    def get_prompt_registry(self) -> MCPPromptRegistry:
        """Get the prompt registry."""
        return self._prompt_registry
    
    def get_recipe_info(self) -> Dict[str, Any]:
        """Get recipe information."""
        if not self._loaded:
            self.load()
        
        return {
            "name": self.recipe_name,
            "version": self._recipe_config.get("version", "1.0.0"),
            "description": self._recipe_config.get("description", ""),
            "author": self._recipe_config.get("author"),
            "tags": self._recipe_config.get("tags", []),
            "tools_count": len(self._tool_registry.list_all()),
            "resources_count": len(self._resource_registry.list_all()),
            "prompts_count": len(self._prompt_registry.list_all()),
        }


def create_recipe_mcp_server(
    recipe_name: str,
    config: Optional[RecipeMCPConfig] = None,
) -> "MCPServer":
    """
    Create an MCP server from a recipe.
    
    Args:
        recipe_name: Name of the recipe
        config: Optional configuration
        
    Returns:
        MCPServer instance ready to run
        
    Example:
        server = create_recipe_mcp_server("support-reply")
        server.run(transport="stdio")
    """
    adapter = RecipeMCPAdapter(recipe_name, config)
    adapter.load()
    return adapter.to_mcp_server()
