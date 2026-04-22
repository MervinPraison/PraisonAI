"""
Bot Smart Defaults Module.

Shared logic for applying sensible bot defaults (tools, auto-approval, memory)
to agents. Used by both the Bot() wrapper and WebSocketGateway to ensure
consistent behavior across all entry points.
"""

import logging
from typing import Any, Optional, List

logger = logging.getLogger(__name__)


def apply_bot_smart_defaults(agent: Any, config: Optional[Any] = None) -> Any:
    """Enhance agent with sensible bot defaults if not already configured.
    
    Smart defaults are applied automatically:
    - Safe tools (search_web, schedule_add/list/remove) if agent has no tools
    - Auto-approval for safe tools if config.auto_approve_tools is True
    - Memory enabled if not already set
    
    These defaults make bots immediately useful without extra configuration.
    Users who want full control can pre-configure their agent or set
    explicit config overrides.
    
    Args:
        agent: Agent instance to enhance (other types like AgentTeam/AgentFlow are left unchanged)
        config: BotConfig instance with settings like auto_approve_tools, default_tools
    
    Returns:
        Enhanced agent (same instance, modified in-place)
    """
    if agent is None:
        return agent
    
    # Only enhance Agent instances (not AgentTeam/AgentFlow)
    agent_cls_name = type(agent).__name__
    if agent_cls_name not in ("Agent",):
        return agent
    
    # Wire BotConfig.auto_approve_tools → Agent(approval=True)
    if config and getattr(config, 'auto_approve_tools', False):
        if getattr(agent, '_approval_backend', None) is None:
            try:
                from praisonaiagents.approval.backends import AutoApproveBackend
                agent._approval_backend = AutoApproveBackend()
                logger.debug(f"Bot: auto_approve_tools enabled for agent '{getattr(agent, 'name', '?')}'")
            except ImportError:
                logger.warning("AutoApproveBackend not available - install praisonaiagents[approval]")
    
    # Wire BotConfig.autonomy → Agent autonomy (if not already enabled)
    autonomy_val = None
    if config:
        autonomy_val = getattr(config, 'autonomy', None)
    if autonomy_val and not getattr(agent, 'autonomy_enabled', False):
        if hasattr(agent, '_init_autonomy'):
            agent._init_autonomy(autonomy_val)
            logger.debug(f"Bot: autonomy enabled for agent '{getattr(agent, 'name', '?')}'")
    
    # Inject session history if agent has no memory configured (zero-dep).
    # NOTE: No session_id here — BotSessionManager handles per-user
    # isolation by swapping chat_history before/after each agent.chat().
    current_memory = getattr(agent, 'memory', None)
    if current_memory is None:
        agent.memory = {
            "history": True,
            "history_limit": 20,
        }
        logger.debug(f"Bot: injected session history for agent '{getattr(agent, 'name', '?')}'")
    
    # Add default tools if agent has none
    # NOTE: Agent class always initializes tools=[], so we check for empty list
    current_tools = getattr(agent, 'tools', None) or []
    if not current_tools:
        # Use safe defaults (exclude destructive tools like execute_command)
        default_safe_tools = _get_default_safe_tools(config)
        
        if default_safe_tools:
            try:
                resolved_tools = _resolve_tool_names(default_safe_tools)
                if resolved_tools:
                    agent.tools = resolved_tools
                    logger.debug(f"Bot: applied {len(resolved_tools)} default safe tools to agent '{getattr(agent, 'name', '?')}'")
                else:
                    # Profile resolution returned empty - try fallback
                    fallback_tools = _get_fallback_tools()
                    if fallback_tools:
                        agent.tools = fallback_tools
                        logger.debug(f"Bot: applied {len(fallback_tools)} fallback tools to agent '{getattr(agent, 'name', '?')}'")
            except Exception as e:
                logger.warning(f"Failed to resolve default tools: {e}")
                # Fallback: hardcoded imports if tool resolution fails
                fallback_tools = _get_fallback_tools()
                if fallback_tools:
                    agent.tools = fallback_tools
                    logger.debug(f"Bot: applied {len(fallback_tools)} fallback tools to agent '{getattr(agent, 'name', '?')}'")
    
    return agent


def _get_default_safe_tools(config: Optional[Any] = None) -> List[str]:
    """Get the list of safe tools to inject by default.
    
    Safe tools are those that don't write to filesystem, execute code, or
    make destructive changes. They auto-approve by default in chat environments.
    
    Args:
        config: BotConfig instance that may override default_tools
        
    Returns:
        List of safe tool names to inject
    """
    # Get safe defaults (exclude destructive tools like execute_command)
    default_safe_tools = [
        "search_web", "web_crawl",
        "schedule_add", "schedule_list", "schedule_remove",
        "store_memory", "search_memory",
        "store_learning", "search_learning",
    ]
    
    # Allow config override, but filter out destructive tools for safety
    if config and hasattr(config, 'default_tools'):
        config_tools = getattr(config, 'default_tools', None) or []
        if config_tools:
            # Filter out known destructive tools unless explicitly allowed
            safe_config_tools = []
            destructive_tools = {"execute_command", "delete_file", "write_file", "shell_command"}
            
            for tool in config_tools:
                if tool in destructive_tools:
                    logger.warning(f"Skipping destructive tool '{tool}' from auto-injection (requires explicit opt-in)")
                    continue
                safe_config_tools.append(tool)
            
            return safe_config_tools
    
    return default_safe_tools


def _resolve_tool_names(tool_names: List[str]) -> list:
    """Resolve tool names to actual tool instances using the tool system."""
    try:
        from praisonaiagents.tools.profiles import resolve_profiles
        from praisonaiagents.tools import ToolResolver
        
        # Try profile resolution first (modern approach)
        profile_map = {
            "search_web": "web", "web_crawl": "web",
            "schedule_add": "schedule", "schedule_list": "schedule", "schedule_remove": "schedule",
            "store_memory": "memory", "search_memory": "memory",
            "store_learning": "learning", "search_learning": "learning",
        }
        
        profiles = set()
        individual_tools = []
        
        for tool_name in tool_names:
            if tool_name in profile_map:
                profiles.add(profile_map[tool_name])
            else:
                individual_tools.append(tool_name)
        
        resolved_tools = []
        
        # Resolve profiles
        if profiles:
            profile_tools = resolve_profiles(*profiles)
            resolved_tools.extend(profile_tools)
        
        # Resolve individual tools
        if individual_tools:
            resolver = ToolResolver()
            individual_resolved = resolver.resolve_many(individual_tools)
            resolved_tools.extend(individual_resolved)
        
        return resolved_tools
        
    except Exception:
        # Fall back to direct imports if profile resolution fails
        return []


def _get_fallback_tools() -> list:
    """Get fallback tool instances when profile resolution fails."""
    fallback_tools = []
    
    # Try individual imports as fallback
    try:
        from praisonaiagents.tools import (
            schedule_add, schedule_list, schedule_remove,
        )
        fallback_tools.extend([schedule_add, schedule_list, schedule_remove])
    except (ImportError, AttributeError):
        pass
    
    try:
        from praisonaiagents.tools import search_web
        fallback_tools.insert(0, search_web)
    except (ImportError, AttributeError):
        pass
    
    try:
        from praisonaiagents.tools import store_memory, search_memory
        fallback_tools.extend([store_memory, search_memory])
    except (ImportError, AttributeError):
        pass
        
    return fallback_tools