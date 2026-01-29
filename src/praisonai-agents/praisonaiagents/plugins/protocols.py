"""
Plugin Protocols for PraisonAI Agents.

Defines the protocol interfaces for plugins, enabling type-safe
plugin development and custom implementations.

Zero Performance Impact:
- Protocols are runtime-checkable but don't add overhead
- No heavy imports at module level
"""

from typing import Any, Dict, List, Protocol, runtime_checkable


@runtime_checkable
class PluginProtocol(Protocol):
    """
    Protocol defining the interface for PraisonAI plugins.
    
    Plugins can extend agent functionality by implementing
    hook methods that are called at various points in the
    agent lifecycle.
    
    Example:
        class MyPlugin:
            @property
            def name(self) -> str:
                return "my_plugin"
            
            @property
            def version(self) -> str:
                return "1.0.0"
            
            def on_init(self, context: Dict[str, Any]) -> None:
                print("Plugin initialized")
            
            def on_shutdown(self) -> None:
                print("Plugin shutdown")
    """
    
    @property
    def name(self) -> str:
        """Get the plugin name."""
        ...
    
    @property
    def version(self) -> str:
        """Get the plugin version."""
        ...
    
    def on_init(self, context: Dict[str, Any]) -> None:
        """Called when plugin is initialized."""
        ...
    
    def on_shutdown(self) -> None:
        """Called when plugin is shutting down."""
        ...


@runtime_checkable
class ToolPluginProtocol(PluginProtocol, Protocol):
    """
    Protocol for plugins that provide tools.
    
    Example:
        class MyToolPlugin:
            @property
            def name(self) -> str:
                return "my_tool_plugin"
            
            @property
            def version(self) -> str:
                return "1.0.0"
            
            def get_tools(self) -> List[Dict[str, Any]]:
                return [{"name": "my_tool", "description": "Does something"}]
    """
    
    def get_tools(self) -> List[Dict[str, Any]]:
        """Return tools provided by this plugin."""
        ...


@runtime_checkable
class HookPluginProtocol(PluginProtocol, Protocol):
    """
    Protocol for plugins that implement lifecycle hooks.
    
    Example:
        class MyHookPlugin:
            @property
            def name(self) -> str:
                return "my_hook_plugin"
            
            @property
            def version(self) -> str:
                return "1.0.0"
            
            def before_tool(self, tool_name: str, args: Dict[str, Any]) -> Dict[str, Any]:
                # Modify args before tool execution
                return args
            
            def after_tool(self, tool_name: str, result: Any) -> Any:
                # Modify result after tool execution
                return result
    """
    
    def before_tool(self, tool_name: str, args: Dict[str, Any]) -> Dict[str, Any]:
        """Called before tool execution. Can modify args."""
        ...
    
    def after_tool(self, tool_name: str, result: Any) -> Any:
        """Called after tool execution. Can modify result."""
        ...


@runtime_checkable
class AgentPluginProtocol(PluginProtocol, Protocol):
    """
    Protocol for plugins that hook into agent lifecycle.
    
    Example:
        class MyAgentPlugin:
            @property
            def name(self) -> str:
                return "my_agent_plugin"
            
            @property
            def version(self) -> str:
                return "1.0.0"
            
            def before_agent(self, prompt: str, context: Dict[str, Any]) -> str:
                # Modify prompt before agent execution
                return prompt
            
            def after_agent(self, response: str, context: Dict[str, Any]) -> str:
                # Modify response after agent execution
                return response
    """
    
    def before_agent(self, prompt: str, context: Dict[str, Any]) -> str:
        """Called before agent execution. Can modify prompt."""
        ...
    
    def after_agent(self, response: str, context: Dict[str, Any]) -> str:
        """Called after agent execution. Can modify response."""
        ...


@runtime_checkable
class LLMPluginProtocol(PluginProtocol, Protocol):
    """
    Protocol for plugins that hook into LLM calls.
    
    Example:
        class MyLLMPlugin:
            @property
            def name(self) -> str:
                return "my_llm_plugin"
            
            @property
            def version(self) -> str:
                return "1.0.0"
            
            def before_llm(self, messages: List[Dict], params: Dict[str, Any]) -> tuple:
                # Modify messages and params before LLM call
                return messages, params
            
            def after_llm(self, response: str, usage: Dict[str, Any]) -> str:
                # Modify response after LLM call
                return response
    """
    
    def before_llm(self, messages: List[Dict], params: Dict[str, Any]) -> tuple:
        """Called before LLM call. Can modify messages and params."""
        ...
    
    def after_llm(self, response: str, usage: Dict[str, Any]) -> str:
        """Called after LLM call. Can modify response."""
        ...
