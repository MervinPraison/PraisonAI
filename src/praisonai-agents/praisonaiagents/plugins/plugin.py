"""
Plugin definitions for PraisonAI Agents.

Provides base plugin class and hook definitions.
"""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


class PluginHook(str, Enum):
    """Available plugin hooks."""
    
    # Lifecycle hooks
    ON_INIT = "on_init"
    ON_SHUTDOWN = "on_shutdown"
    
    # Agent hooks
    BEFORE_AGENT = "before_agent"
    AFTER_AGENT = "after_agent"
    
    # Tool hooks
    BEFORE_TOOL = "before_tool"
    AFTER_TOOL = "after_tool"
    
    # Message hooks (for bot/channel integrations)
    BEFORE_MESSAGE = "before_message"
    AFTER_MESSAGE = "after_message"
    MESSAGE_RECEIVED = "message_received"
    MESSAGE_SENDING = "message_sending"
    MESSAGE_SENT = "message_sent"
    
    # LLM hooks
    BEFORE_LLM = "before_llm"
    AFTER_LLM = "after_llm"
    
    # Session hooks
    SESSION_START = "session_start"
    SESSION_END = "session_end"
    
    # Gateway hooks
    GATEWAY_START = "gateway_start"
    GATEWAY_STOP = "gateway_stop"
    
    # Compaction hooks (memory management)
    BEFORE_COMPACTION = "before_compaction"
    AFTER_COMPACTION = "after_compaction"
    
    # Tool result persistence (for modifying tool results before storage)
    TOOL_RESULT_PERSIST = "tool_result_persist"
    
    # Permission hooks
    ON_PERMISSION_ASK = "on_permission_ask"
    
    # Config hooks
    ON_CONFIG = "on_config"
    
    # Auth hooks
    ON_AUTH = "on_auth"
    
    # Error hooks
    ON_ERROR = "on_error"
    ON_RETRY = "on_retry"
    
    # Claude Code parity hooks
    USER_PROMPT_SUBMIT = "user_prompt_submit"  # When user submits a prompt
    NOTIFICATION = "notification"              # When notification is sent
    SUBAGENT_STOP = "subagent_stop"           # When subagent completes
    SETUP = "setup"                           # On initialization/maintenance


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
