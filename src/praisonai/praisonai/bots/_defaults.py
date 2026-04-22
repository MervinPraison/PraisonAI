"""
Bot Smart Defaults Module.

Shared logic for applying sensible bot defaults (tools, auto-approval, memory)
to agents. Used by both the Bot() wrapper and WebSocketGateway to ensure
consistent behavior across all entry points.
"""

import logging
from typing import Any, Optional, List

logger = logging.getLogger(__name__)


def apply_bot_smart_defaults(agent: Any, config: Optional[Any] = None, session_key: str = "default") -> Any:
    """Enhance agent with sensible bot defaults if not already configured.
    
    Smart defaults are applied automatically:
    - Workspace containment for file operations
    - Safe tools (search_web, schedule_add/list/remove, file tools) if agent has no tools
    - Auto-approval for safe tools if config.auto_approve_tools is True
    - Memory enabled if not already set
    
    These defaults make bots immediately useful without extra configuration.
    Users who want full control can pre-configure their agent or set
    explicit config overrides.
    
    Args:
        agent: Agent instance to enhance (other types like AgentTeam/AgentFlow are left unchanged)
        config: BotConfig instance with settings like auto_approve_tools, default_tools
        session_key: Session identifier for workspace resolution
    
    Returns:
        Enhanced agent (same instance, modified in-place)
    """
    if agent is None:
        return agent
    
    # Only enhance Agent instances (not AgentTeam/AgentFlow). Use isinstance so
    # user subclasses of Agent also receive smart defaults.
    try:
        from praisonaiagents import Agent as _Agent
    except ImportError:
        return agent
    if not isinstance(agent, _Agent):
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
    
    # Setup workspace for file operations containment
    workspace = None
    try:
        from praisonaiagents.workspace import Workspace
        workspace = Workspace.from_config(config, session_key=session_key)
        # Store workspace on agent for tool factories to use
        agent._workspace = workspace
        logger.debug(f"Bot: configured workspace at {workspace.root} for agent '{getattr(agent, 'name', '?')}'")
    except Exception as e:
        logger.warning(f"Failed to setup workspace: {e}")
    
    # Add default tools if agent has none (unless explicitly set to empty)
    # NOTE: Agent class always initializes tools=[], so we check for empty list
    # Don't inject defaults if user explicitly specified tools: [] in YAML
    current_tools = getattr(agent, 'tools', None) or []
    explicit_empty = getattr(agent, '_explicit_empty_tools', False)
    if not current_tools and not explicit_empty:
        # Use safe defaults (exclude destructive tools like execute_command)
        default_safe_tools = _get_default_safe_tools(config, workspace=workspace)
        
        if default_safe_tools:
            try:
                resolved_tools = _resolve_tool_names_with_workspace(default_safe_tools, workspace)
            except (ImportError, AttributeError) as e:
                logger.warning(f"Failed to resolve default tools: {e}")
                resolved_tools = []
            if not resolved_tools:
                resolved_tools = _get_fallback_tools_with_workspace(workspace)
            if resolved_tools:
                agent.tools = resolved_tools
                logger.debug(
                    f"Bot: applied {len(resolved_tools)} default tools to agent "
                    f"'{getattr(agent, 'name', '?')}'"
                )
    
    return agent


def _get_default_safe_tools(config: Optional[Any] = None, workspace=None) -> List[str]:
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
            # File tools are safe only when a workspace is actually configured.
            destructive_tools = {"execute_command", "shell_command"}
            if workspace is None:
                destructive_tools |= {
                    "write_file", "edit_file", "delete_file", "skill_manage",
                }
            
            for tool in config_tools:
                if tool in destructive_tools:
                    logger.warning(f"Skipping destructive tool '{tool}' from auto-injection (requires explicit opt-in)")
                    continue
                safe_config_tools.append(tool)
            
            return safe_config_tools
    
    return default_safe_tools


def _resolve_tool_names_with_workspace(tool_names: List[str], workspace=None) -> list:
    """Resolve tool names to actual tool instances with workspace support."""
    try:
        from praisonaiagents.tools.profiles import resolve_profiles
        from praisonaiagents.tools import ToolResolver
        
        # Split into workspace-aware and regular tools
        workspace_tools = {
            "read_file", "write_file", "edit_file", "list_files", "search_files",
            "skill_manage", "skills_list", "skill_view",
            "todo_add", "todo_list", "todo_update",
            "session_search", "delegate_task"
        }
        
        # Try profile resolution first (modern approach)
        profile_map = {
            "search_web": "web", "web_crawl": "web",
            "schedule_add": "schedule", "schedule_list": "schedule", "schedule_remove": "schedule",
            "store_memory": "memory", "search_memory": "memory",
            "store_learning": "learning", "search_learning": "learning",
        }
        
        profiles = set()
        individual_tools = []
        workspace_tool_names = []
        
        for tool_name in tool_names:
            if tool_name in workspace_tools:
                workspace_tool_names.append(tool_name)
            elif tool_name in profile_map:
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
        
        # Create workspace-aware tool instances
        if workspace_tool_names and workspace:
            workspace_resolved = _create_workspace_tools(workspace_tool_names, workspace)
            resolved_tools.extend(workspace_resolved)
        
        return resolved_tools
        
    except (ImportError, AttributeError):
        # Fall back to direct imports if profile resolution fails
        return []


def _create_workspace_tools(tool_names: List[str], workspace) -> list:
    """Create workspace-aware tool instances."""
    tools = []
    
    try:
        # File tools
        if any(name in ["read_file", "write_file", "edit_file", "list_files", "search_files"] for name in tool_names):
            from praisonaiagents.tools.file_tools import create_file_tools
            file_tools = create_file_tools(workspace=workspace)
            
            if "read_file" in tool_names:
                tools.append(file_tools.read_file)
            if "write_file" in tool_names:
                tools.append(file_tools.write_file)
            if "list_files" in tool_names:
                tools.append(file_tools.list_files)
        
        # Edit tools
        if any(name in ["edit_file", "search_files"] for name in tool_names):
            from praisonaiagents.tools.edit_tools import create_edit_tools
            edit_tools = create_edit_tools(workspace=workspace)
            
            if "edit_file" in tool_names:
                tools.append(edit_tools.edit_file)
            if "search_files" in tool_names:
                tools.append(edit_tools.search_files)
        
        # Skill management tools  
        if any(name in ["skill_manage", "skills_list", "skill_view"] for name in tool_names):
            from praisonaiagents.tools.skill_tools import create_skill_tools
            skill_tools = create_skill_tools(workspace=workspace)
            
            if "skill_manage" in tool_names:
                tools.append(skill_tools.skill_manage)
            if "skills_list" in tool_names:
                tools.append(skill_tools.skills_list)
            if "skill_view" in tool_names:
                tools.append(skill_tools.skill_view)
        
        # Todo/planning tools
        if any(name in ["todo_add", "todo_list", "todo_update"] for name in tool_names):
            from praisonaiagents.tools.todo_tools import create_todo_tools
            todo_tools = create_todo_tools(workspace=workspace)
            
            if "todo_add" in tool_names:
                tools.append(todo_tools.todo_add)
            if "todo_list" in tool_names:
                tools.append(todo_tools.todo_list)
            if "todo_update" in tool_names:
                tools.append(todo_tools.todo_update)
        
        # Session tools
        if "session_search" in tool_names:
            from praisonaiagents.tools.session_tools import create_session_tools
            session_tools = create_session_tools(workspace=workspace)
            tools.append(session_tools.session_search)
        
        # Delegation tools
        if "delegate_task" in tool_names:
            from praisonaiagents.tools.delegation_tools import create_delegation_tools
            delegation_tools = create_delegation_tools(workspace=workspace)
            tools.append(delegation_tools.delegate_task)
                
    except (ImportError, AttributeError) as e:
        logger.warning(f"Failed to create workspace tools: {e}")
    
    return tools


def _get_fallback_tools_with_workspace(workspace=None) -> list:
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
    
    # Add workspace-aware file tools as fallback
    if workspace:
        try:
            from praisonaiagents.tools.file_tools import create_file_tools
            file_tools = create_file_tools(workspace=workspace)
            fallback_tools.extend([file_tools.read_file, file_tools.write_file, file_tools.list_files])
        except (ImportError, AttributeError):
            pass
        
    return fallback_tools