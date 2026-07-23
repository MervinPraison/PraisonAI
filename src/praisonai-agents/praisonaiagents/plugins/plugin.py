"""
Plugin definitions for PraisonAI Agents.

Provides base plugin class and hook definitions.
PluginHook is now an alias for HookEvent (DRY compliance).
"""

import logging
from praisonaiagents._logging import get_logger
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Union

# Import HookEvent at module level for alias (DRY)
from ..hooks.types import HookEvent

logger = get_logger(__name__)

# PluginHook is now an alias for HookEvent - single source of truth
PluginHook = HookEvent


class GuardrailBlocked(Exception):
    """Raised by a plugin lifecycle method to block/deny the current action.

    A ``POLICY``/``GUARDRAIL`` plugin can raise this from any ``before_*``
    method (``before_tool``, ``before_llm``, ``before_agent``,
    ``before_message``) to stop the tool call / LLM request / agent run /
    inbound message. The plugin bridge converts it into a denying
    ``HookResult`` so the runtime's existing ``is_blocked`` enforcement skips
    the action and surfaces ``reason``.
    """

    def __init__(self, reason: str = "Blocked by guardrail plugin"):
        self.reason = reason
        super().__init__(reason)


class PluginDecision:
    """Lightweight deny/block signal a plugin method can return.

    This is an alternative to returning a full ``HookResult`` (which requires
    importing from ``hooks.types``) or raising :class:`GuardrailBlocked`. Return
    ``PluginDecision.deny(reason)`` or ``PluginDecision.block(reason)`` from a
    ``before_*`` method to stop the action; the bridge forwards it to the
    runtime's block enforcement. Returning ``allow()`` (or the usual
    ``dict``/``str``/``tuple``/``None``) keeps today's rewrite/no-op semantics.
    """

    __slots__ = ("decision", "reason")

    def __init__(self, decision: str, reason: Optional[str] = None):
        self.decision = decision
        self.reason = reason

    @classmethod
    def allow(cls, reason: Optional[str] = None) -> "PluginDecision":
        return cls("allow", reason)

    @classmethod
    def deny(cls, reason: str) -> "PluginDecision":
        return cls("deny", reason)

    @classmethod
    def block(cls, reason: str) -> "PluginDecision":
        return cls("block", reason)

    def is_denied(self) -> bool:
        return self.decision in ("deny", "block")

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
    
    def session_start(self, context: Dict[str, Any]) -> None:
        """Called when a session starts. Observe-only (source, session_name, etc.)."""
        pass

    def session_end(self, context: Dict[str, Any]) -> None:
        """Called when a session ends. Observe-only (reason, total_turns, etc.)."""
        pass

    def on_error(self, error_type: str, error_message: str, context: Dict[str, Any]) -> None:
        """Called when an error occurs during agent execution. Observe-only."""
        pass

    def before_agent(
        self, prompt: str, context: Dict[str, Any]
    ) -> Union[str, "PluginDecision", None]:
        """Called before agent execution.

        Return a modified ``prompt`` (rewrite), or a deny/block decision
        (``PluginDecision.deny(reason)`` / a ``HookResult`` / raise
        :class:`GuardrailBlocked`) to abort the run, or ``None`` for no-op.
        """
        return prompt
    
    def after_agent(self, response: str, context: Dict[str, Any]) -> str:
        """Called after agent execution. Can modify response."""
        return response
    
    def before_tool(
        self, tool_name: str, args: Dict[str, Any]
    ) -> Union[Dict[str, Any], "PluginDecision", None]:
        """Called before tool execution.

        Return modified ``args`` (rewrite), or a deny/block decision
        (``PluginDecision.deny(reason)`` / a ``HookResult`` / raise
        :class:`GuardrailBlocked`) to skip the tool call, or ``None`` for no-op.
        """
        return args
    
    def after_tool(self, tool_name: str, result: Any) -> Any:
        """Called after tool execution. Can modify result."""
        return result

    def before_tool_definitions(
        self, tool_definitions: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Called after advertised tool definitions are assembled and before
        they reach the LLM. Can inspect, filter, or rewrite them."""
        return tool_definitions
    
    def before_message(
        self, message: Dict[str, Any]
    ) -> Union[Dict[str, Any], "PluginDecision", None]:
        """Called before message is processed.

        Return a modified ``message`` (rewrite), or a deny/block decision
        (``PluginDecision.deny(reason)`` / a ``HookResult`` / raise
        :class:`GuardrailBlocked`) to drop the inbound message, or ``None``.
        """
        return message
    
    def after_message(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """Called after message is processed. Can modify message."""
        return message
    
    def before_llm(
        self, messages: List[Dict], params: Dict[str, Any]
    ) -> Union[tuple, "PluginDecision", None]:
        """Called before LLM call.

        Return a ``(messages, params)`` tuple (rewrite), or a deny/block
        decision (``PluginDecision.deny(reason)`` / a ``HookResult`` / raise
        :class:`GuardrailBlocked`) to refuse the LLM request, or ``None``.
        """
        return messages, params
    
    def after_llm(self, response: str, usage: Dict[str, Any]) -> str:
        """Called after LLM call. Can modify response."""
        return response

    def cli_backend_execute(self, context: Dict[str, Any]) -> None:
        """Called after a CLI backend delegates a turn. Observe-only."""
        pass
    
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
