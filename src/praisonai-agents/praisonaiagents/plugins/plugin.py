"""
Plugin definitions for PraisonAI Agents.

Provides base plugin class and hook definitions.
PluginHook is now an alias for HookEvent (DRY compliance).
"""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

# Import HookEvent at module level for alias (DRY)
from ..hooks.types import HookEvent

logger = logging.getLogger(__name__)

# PluginHook is now an alias for HookEvent - single source of truth
PluginHook = HookEvent


class PluginType(str, Enum):
    """Types of plugins that can be registered.
    
    Used to categorize plugins and enable type-specific discovery.
    """
    TOOL = "tool"           # Provides tools for agents
    HOOK = "hook"           # Intercepts lifecycle events
    SKILL = "skill"         # Provides agent capabilities (SKILL.md)
    POLICY = "policy"       # Provides execution rules
    GUARDRAIL = "guardrail" # Provides validation rules
    INTEGRATION = "integration"  # External tool integrations


@dataclass
class PluginInfo:
    """Plugin metadata."""
    
    name: str
    version: str = "1.0.0"
    description: str = ""
    author: str = ""
    hooks: List[PluginHook] = field(default_factory=list)
    dependencies: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "author": self.author,
            "hooks": [h.value for h in self.hooks],
            "dependencies": self.dependencies,
        }


class Plugin(ABC):
    """
    Base class for PraisonAI plugins.
    
    Plugins can extend agent functionality by implementing
    hook methods that are called at various points in the
    agent lifecycle.
    
    Example:
        class MyPlugin(Plugin):
            @property
            def info(self) -> PluginInfo:
                return PluginInfo(
                    name="my_plugin",
                    version="1.0.0",
                    hooks=[PluginHook.BEFORE_TOOL]
                )
            
            def before_tool(self, tool_name: str, args: dict) -> dict:
                # Modify args before tool execution
                return args
    """
    
    @property
    @abstractmethod
    def info(self) -> PluginInfo:
        """Get plugin information."""
        pass
    
    def on_init(self, context: Dict[str, Any]) -> None:
        """Called when plugin is initialized."""
        pass
    
    def on_shutdown(self) -> None:
        """Called when plugin is shutting down."""
        pass
    
    def before_agent(self, prompt: str, context: Dict[str, Any]) -> str:
        """Called before agent execution. Can modify prompt."""
        return prompt
    
    def after_agent(self, response: str, context: Dict[str, Any]) -> str:
        """Called after agent execution. Can modify response."""
        return response
    
    def before_tool(self, tool_name: str, args: Dict[str, Any]) -> Dict[str, Any]:
        """Called before tool execution. Can modify args."""
        return args
    
    def after_tool(self, tool_name: str, result: Any) -> Any:
        """Called after tool execution. Can modify result."""
        return result
    
    def before_message(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """Called before message is processed. Can modify message."""
        return message
    
    def after_message(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """Called after message is processed. Can modify message."""
        return message
    
    def before_llm(self, messages: List[Dict], params: Dict[str, Any]) -> tuple:
        """Called before LLM call. Can modify messages and params."""
        return messages, params
    
    def after_llm(self, response: str, usage: Dict[str, Any]) -> str:
        """Called after LLM call. Can modify response."""
        return response
    
    def on_permission_ask(self, target: str, reason: str) -> Optional[bool]:
        """Called when permission is requested. Return True/False to auto-approve/deny."""
        return None
    
    def on_config(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Called to modify configuration."""
        return config
    
    def on_auth(self, auth_type: str, credentials: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Called for authentication. Return credentials or None."""
        return None
    
    def get_tools(self) -> List[Dict[str, Any]]:
        """Return additional tools provided by this plugin."""
        return []


class FunctionPlugin(Plugin):
    """
    A simple plugin that wraps functions for specific hooks.
    
    Example:
        def my_before_tool(tool_name, args):
            return args
        
        plugin = FunctionPlugin(
            name="my_plugin",
            hooks={PluginHook.BEFORE_TOOL: my_before_tool}
        )
    """
    
    def __init__(
        self,
        name: str,
        hooks: Optional[Dict[PluginHook, Callable]] = None,
        version: str = "1.0.0",
        description: str = "",
    ):
        self._name = name
        self._hooks = hooks or {}
        self._version = version
        self._description = description
    
    @property
    def info(self) -> PluginInfo:
        return PluginInfo(
            name=self._name,
            version=self._version,
            description=self._description,
            hooks=list(self._hooks.keys()),
        )
    
    def before_tool(self, tool_name: str, args: Dict[str, Any]) -> Dict[str, Any]:
        if PluginHook.BEFORE_TOOL in self._hooks:
            return self._hooks[PluginHook.BEFORE_TOOL](tool_name, args)
        return args
    
    def after_tool(self, tool_name: str, result: Any) -> Any:
        if PluginHook.AFTER_TOOL in self._hooks:
            return self._hooks[PluginHook.AFTER_TOOL](tool_name, result)
        return result
    
    def before_agent(self, prompt: str, context: Dict[str, Any]) -> str:
        if PluginHook.BEFORE_AGENT in self._hooks:
            return self._hooks[PluginHook.BEFORE_AGENT](prompt, context)
        return prompt
    
    def after_agent(self, response: str, context: Dict[str, Any]) -> str:
        if PluginHook.AFTER_AGENT in self._hooks:
            return self._hooks[PluginHook.AFTER_AGENT](response, context)
        return response
