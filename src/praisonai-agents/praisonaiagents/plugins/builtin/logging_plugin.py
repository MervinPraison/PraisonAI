"""
Logging Plugin for PraisonAI Agents.

Provides structured logging for agent lifecycle events.
"""

import logging
from typing import Any, Dict, List

from ..plugin import Plugin, PluginInfo, PluginHook

logger = logging.getLogger("praisonaiagents.plugins.logging")


class LoggingPlugin(Plugin):
    """
    Plugin that logs agent lifecycle events.
    
    Useful for debugging and monitoring agent behavior.
    
    Example:
        from praisonaiagents.plugins import PluginManager
        from praisonaiagents.plugins.builtin import LoggingPlugin
        
        manager = PluginManager()
        manager.register(LoggingPlugin(level=logging.DEBUG))
    """
    
    def __init__(
        self,
        level: int = logging.INFO,
        log_tools: bool = True,
        log_agents: bool = True,
        log_llm: bool = False,
    ):
        """
        Initialize the logging plugin.
        
        Args:
            level: Logging level (default: INFO)
            log_tools: Whether to log tool events
            log_agents: Whether to log agent events
            log_llm: Whether to log LLM events
        """
        self._level = level
        self._log_tools = log_tools
        self._log_agents = log_agents
        self._log_llm = log_llm
        
        self._hooks = []
        if log_tools:
            self._hooks.extend([PluginHook.BEFORE_TOOL, PluginHook.AFTER_TOOL])
        if log_agents:
            self._hooks.extend([PluginHook.BEFORE_AGENT, PluginHook.AFTER_AGENT])
        if log_llm:
            self._hooks.extend([PluginHook.BEFORE_LLM, PluginHook.AFTER_LLM])
    
    @property
    def info(self) -> PluginInfo:
        return PluginInfo(
            name="logging",
            version="1.0.0",
            description="Logs agent lifecycle events for debugging and monitoring",
            author="PraisonAI",
            hooks=self._hooks,
        )
    
    def on_init(self, context: Dict[str, Any]) -> None:
        logger.log(self._level, "LoggingPlugin initialized")
    
    def on_shutdown(self) -> None:
        logger.log(self._level, "LoggingPlugin shutdown")
    
    def before_tool(self, tool_name: str, args: Dict[str, Any]) -> Dict[str, Any]:
        logger.log(
            self._level,
            f"[TOOL] Before: {tool_name}",
            extra={"tool_name": tool_name, "args": args}
        )
        return args
    
    def after_tool(self, tool_name: str, result: Any) -> Any:
        result_preview = str(result)[:100] if result else "None"
        logger.log(
            self._level,
            f"[TOOL] After: {tool_name} -> {result_preview}",
            extra={"tool_name": tool_name, "result_preview": result_preview}
        )
        return result
    
    def before_agent(self, prompt: str, context: Dict[str, Any]) -> str:
        prompt_preview = prompt[:100] if prompt else ""
        logger.log(
            self._level,
            f"[AGENT] Before: {prompt_preview}...",
            extra={"prompt_preview": prompt_preview}
        )
        return prompt
    
    def after_agent(self, response: str, context: Dict[str, Any]) -> str:
        response_preview = response[:100] if response else ""
        logger.log(
            self._level,
            f"[AGENT] After: {response_preview}...",
            extra={"response_preview": response_preview}
        )
        return response
    
    def before_llm(self, messages: List[Dict], params: Dict[str, Any]) -> tuple:
        logger.log(
            self._level,
            f"[LLM] Before: {len(messages)} messages",
            extra={"message_count": len(messages), "params": params}
        )
        return messages, params
    
    def after_llm(self, response: str, usage: Dict[str, Any]) -> str:
        response_preview = response[:100] if response else ""
        logger.log(
            self._level,
            f"[LLM] After: {response_preview}...",
            extra={"response_preview": response_preview, "usage": usage}
        )
        return response
