"""
Bot Smart Defaults Module.

Shared logic for applying sensible bot defaults (tools, auto-approval, memory)
to agents. Used by both the Bot() wrapper and WebSocketGateway to ensure
consistent behavior across all entry points.
"""

import logging
import os
from typing import Any, Optional, List, Dict

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
        # Root change-tracking (/undo) at the workspace the file tools write to,
        # not the gateway process cwd (bug: /undo tracked the wrong directory).
        _set_root = getattr(agent, "set_snapshot_root", None)
        if callable(_set_root):
            try:
                _set_root(str(workspace.root))
            except Exception as e:  # pragma: no cover - defensive
                logger.debug(f"Failed to root snapshot at workspace: {e}")
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
        from praisonai_bot._code_bridge import import_code_module

        ToolResolver = import_code_module("praisonai_code.tool_resolver").ToolResolver
        
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


_SHELL_TOOL_NAMES = frozenset({"execute_command", "shell_command", "acp_execute_command"})

_APPROVER_ENV = {
    "slack": "SLACK_APPROVERS",
    "telegram": "TELEGRAM_APPROVERS",
    "discord": "DISCORD_APPROVERS",
}


def _parse_shell_approvers(ch_cfg: Dict[str, Any], channel_type: str) -> List[str]:
    env_key = _APPROVER_ENV.get(channel_type, "")
    approvers_raw = ch_cfg.get("approval_users") or (os.environ.get(env_key, "") if env_key else "")
    if isinstance(approvers_raw, str):
        return [u.strip() for u in approvers_raw.split(",") if u.strip()]
    if isinstance(approvers_raw, list):
        return [str(u).strip() for u in approvers_raw if str(u).strip()]
    return []


def _channel_token(config: Optional[Any], ch_cfg: Dict[str, Any]) -> Optional[str]:
    token = ch_cfg.get("token") or (getattr(config, "token", None) if config else None)
    return str(token) if token else None


def _sync_approval_registry(agent: Any) -> None:
    """Mirror ``agent._approval_backend`` onto the approval registry.

    Tool functions decorated with ``@require_approval`` consult the registry
    (often with ``agent_name=None``), so the agent backend alone is not enough
    for bot/gateway shell paths.
    """
    backend = getattr(agent, "_approval_backend", None)
    if backend is None:
        return
    try:
        from praisonaiagents.approval import get_approval_registry

        reg = get_approval_registry()
        agent_name = getattr(agent, "name", None)
        if agent_name:
            reg.set_backend(backend, agent_name=agent_name)
    except ImportError:
        logger.warning("Approval registry unavailable — shell approval may prompt in CLI")


def _wire_shell_approval_backend(
    agent: Any,
    *,
    channel_type: str,
    config: Optional[Any],
    ch_cfg: Dict[str, Any],
    allowed_approvers: List[str],
) -> None:
    """Attach a platform or gateway approval backend when auto-approve is off."""
    approval_mode = str(ch_cfg.get("approval_mode") or "channel").strip().lower()
    token = _channel_token(config, ch_cfg)
    approvers = allowed_approvers or None

    if approval_mode == "gateway":
        try:
            from praisonai_bot.gateway.gateway_approval import GatewayApprovalBackend

            agent._approval_backend = GatewayApprovalBackend()
            return
        except ImportError:
            logger.warning("GatewayApprovalBackend unavailable for allow_shell")

    if approval_mode == "http":
        try:
            from praisonai_bot.bots import HTTPApproval

            agent._approval_backend = HTTPApproval(
                host=str(ch_cfg.get("approval_http_host") or "127.0.0.1"),
                port=int(ch_cfg.get("approval_http_port") or 8899),
            )
            return
        except ImportError:
            logger.warning("HTTPApproval unavailable for allow_shell")

    webhook_url = ch_cfg.get("approval_webhook_url") or os.environ.get("APPROVAL_WEBHOOK_URL")
    if approval_mode == "webhook" or webhook_url:
        if not webhook_url:
            logger.warning(
                "approval_mode=webhook requires approval_webhook_url or "
                "APPROVAL_WEBHOOK_URL — falling back to gateway approval queue"
            )
        else:
            try:
                from praisonai_bot.bots import WebhookApproval

                agent._approval_backend = WebhookApproval(webhook_url=str(webhook_url))
                return
            except (ImportError, ValueError) as exc:
                logger.warning("WebhookApproval unavailable for allow_shell: %s", exc)

    if channel_type == "slack":
        approval_channel = (
            ch_cfg.get("approval_channel")
            or (getattr(config, "owner_user_id", None) if config else None)
            or os.environ.get("SLACK_APPROVAL_CHANNEL")
        )
        if approval_channel:
            try:
                from praisonai_bot.bots import SlackApproval

                agent._approval_backend = SlackApproval(
                    token=token,
                    channel=str(approval_channel),
                    allowed_approvers=approvers,
                )
                return
            except ImportError:
                logger.warning("SlackApproval unavailable for allow_shell")

    elif channel_type == "telegram":
        chat_id = (
            ch_cfg.get("approval_channel")
            or (getattr(config, "owner_user_id", None) if config else None)
            or os.environ.get("TELEGRAM_CHAT_ID")
        )
        if chat_id:
            try:
                from praisonai_bot.bots import TelegramApproval

                agent._approval_backend = TelegramApproval(
                    token=token,
                    chat_id=str(chat_id),
                    allowed_approvers=approvers,
                )
                return
            except ImportError:
                logger.warning("TelegramApproval unavailable for allow_shell")

    elif channel_type == "discord":
        channel_id = (
            ch_cfg.get("approval_channel")
            or ch_cfg.get("home_channel")
            or os.environ.get("DISCORD_APPROVAL_CHANNEL")
        )
        if channel_id:
            try:
                from praisonai_bot.bots import DiscordApproval

                agent._approval_backend = DiscordApproval(
                    token=token,
                    channel_id=str(channel_id),
                    allowed_approvers=approvers,
                )
                return
            except ImportError:
                logger.warning("DiscordApproval unavailable for allow_shell")

    try:
        from praisonai_bot.gateway.gateway_approval import GatewayApprovalBackend

        agent._approval_backend = GatewayApprovalBackend()
        logger.info(
            "Shell approval falling back to gateway queue for channel %r",
            channel_type or "?",
        )
        return
    except ImportError:
        pass

    # No usable approval backend could be wired. A prior apply_bot_smart_defaults()
    # may have installed an AutoApproveBackend (config.auto_approve_tools). Leaving it
    # in place would silently auto-approve shell despite the explicit opt-out, so fail
    # closed: replace it with a deny-by-default backend that rejects shell commands.
    from praisonaiagents.approval.backends import AutoApproveBackend

    backend = getattr(agent, "_approval_backend", None)
    if backend is None or isinstance(backend, AutoApproveBackend):
        try:
            from praisonaiagents.approval.backends import CallbackBackend
            from praisonaiagents.approval.protocols import ApprovalDecision

            def _deny_shell(tool_name, arguments, risk_level):
                if tool_name in _SHELL_TOOL_NAMES:
                    return ApprovalDecision(
                        approved=False,
                        reason="shell auto-approval disabled; no approval backend configured",
                        approver="system",
                    )
                return ApprovalDecision(approved=True, reason="auto-approved", approver="system")

            agent._approval_backend = CallbackBackend(_deny_shell)
        except ImportError:  # pragma: no cover - core always present in-tree
            agent._approval_backend = None
    logger.warning(
        "allow_shell with auto_approve_shell=false needs approval_channel, "
        "approval_mode (gateway|http|webhook), or a custom approval backend on the agent "
        "— shell commands will be denied until one is configured"
    )


def enable_shell_tools(
    agent: Any,
    config: Optional[Any] = None,
    ch_cfg: Optional[Dict[str, Any]] = None,
    *,
    channel_type: str = "",
) -> Any:
    """Opt-in shell execution for inbound channel bots (Slack, Telegram, etc.)."""
    if agent is None:
        return agent

    ch_cfg = ch_cfg or {}
    if not ch_cfg.get("allow_shell"):
        return agent

    tools = list(getattr(agent, "tools", None) or [])
    existing = {
        getattr(t, "name", None) or getattr(t, "__name__", "")
        for t in tools
    }
    if "execute_command" not in existing:
        try:
            from praisonaiagents.tools import execute_command

            tools.append(execute_command)
            agent.tools = tools
        except ImportError:
            logger.warning("execute_command unavailable — install praisonaiagents with shell tools")

    instructions = getattr(agent, "instructions", "") or ""
    if "execute_command" not in instructions.lower():
        agent.instructions = (
            instructions
            + "\n\nYou can run shell commands on the bot server using the execute_command tool."
        ).strip()

    deny = set(getattr(agent, "_perm_deny", None) or frozenset())
    deny -= _SHELL_TOOL_NAMES
    agent._perm_deny = frozenset(deny)

    auto_approve = ch_cfg.get("auto_approve_shell", True)
    if isinstance(auto_approve, str):
        auto_approve = auto_approve.strip().lower() in ("1", "true", "yes", "on")

    if auto_approve:
        try:
            from praisonaiagents.approval.backends import AutoApproveBackend

            agent._approval_backend = AutoApproveBackend()
        except ImportError:
            logger.warning("AutoApproveBackend unavailable for allow_shell")
    else:
        _wire_shell_approval_backend(
            agent,
            channel_type=channel_type,
            config=config,
            ch_cfg=ch_cfg,
            allowed_approvers=_parse_shell_approvers(ch_cfg, channel_type),
        )

    _sync_approval_registry(agent)

    logger.info(
        "Shell tools enabled for agent %r on channel %r (auto_approve_shell=%s)",
        getattr(agent, "name", "?"),
        channel_type or "?",
        auto_approve,
    )
    return agent