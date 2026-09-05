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
    memory_was_injected = current_memory is None
    if memory_was_injected:
        agent.memory = {
            "history": True,
            "history_limit": 20,
        }
        logger.debug(f"Bot: injected session history for agent '{getattr(agent, 'name', '?')}'")

    # Enable the coordinated session-learning posture by default (Issue #4864).
    # The always-on gateway/bot is the flagship "assistant that learns who you
    # are across sessions" surface, so an out-of-the-box bot should accrue
    # persona/preferences from the relationship. This reuses the core
    # ``Agent(learn=True)`` posture (auto_memory + conversational-aware nudge
    # cadence) rather than adding any new bot knob. Opt-out with ``learn: false``
    # in the bot config; a pre-configured agent (learn already set) is untouched.
    # ``memory_was_injected`` tells the helper it may safely rebuild the memory
    # backend with a LearnManager; a user-supplied memory is never rewritten.
    _enable_bot_learning(agent, config, memory_was_injected=memory_was_injected)
    
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


def _config_learn_value(config: Optional[Any]) -> Any:
    """Read the operator's ``learn``/``session_learning`` intent from config.

    ``BotConfig`` has no native ``learn`` field, so the gateway forwards the
    YAML key through ``config.metadata`` (the same passthrough used for ``stt``
    / ``voice``). Direct callers may also set an attribute or pass a mapping.
    Checked in order: attribute, ``config.metadata[...]``, mapping key. Returns
    the first non-None value found, else ``None`` ("unset").
    """
    if config is None:
        return None
    metadata = getattr(config, "metadata", None)
    for key in ("learn", "session_learning"):
        val = getattr(config, key, None)
        if val is not None:
            return val
        if isinstance(metadata, dict) and metadata.get(key) is not None:
            return metadata.get(key)
        if isinstance(config, dict) and config.get(key) is not None:
            return config.get(key)
    return None


def _learning_opt_out(config: Optional[Any]) -> bool:
    """Return True when the bot config explicitly disables session learning.

    Opt-out via ``learn: false`` (or ``session_learning: false``) in the bot
    config. Absence means "use the sensible default" (enabled).
    """
    val = _config_learn_value(config)
    if val is None:
        return False
    if isinstance(val, bool):
        return not val
    if isinstance(val, str):
        return val.strip().lower() in ("false", "0", "no", "off", "disabled")
    return False


def _enable_bot_learning(
    agent: Any, config: Optional[Any] = None, memory_was_injected: bool = False
) -> None:
    """Turn on the coordinated session-learning posture for a bot agent.

    Reuses the core ``Agent(learn=True)`` posture (Issue #4864): AGENTIC
    extraction + conversational-aware nudge cadence + auto_memory. This is the
    default for gateway/bot agents so the flagship "assistant that learns who
    you are" surface actually accrues persona/preferences from plain chat.

    No-ops when learning is already configured on the agent (pre-configured
    agents win), when the operator opts out (``learn: false``), or when the
    core learn machinery is unavailable.
    """
    # Respect a pre-configured agent: if the developer already set learn=,
    # leave their choice untouched (including an explicit learn=False opt-out,
    # which leaves _learn_config None but sets _learn_enabled=False).
    if getattr(agent, "_learn_config", None) is not None:
        return
    if getattr(agent, "_learn_enabled", None) is not None:
        return
    if _learning_opt_out(config):
        logger.debug("Bot: session learning opted out via config")
        return

    try:
        from praisonaiagents.config.feature_configs import LearnConfig
        from praisonaiagents.memory.learn.protocols import LearnMode
    except ImportError:
        logger.debug("Bot: learn machinery unavailable — skipping session learning")
        return

    # Same coordinated posture as core Agent(learn=True): conversational turns
    # count (nudge_min_tool_iters=0) and a cheap periodic cadence.
    learn_config = LearnConfig(
        mode=LearnMode.AGENTIC,
        nudge_interval=10,
        nudge_min_tool_iters=0,
    )

    # The nudge cadence only needs _learn_config, so it is always safe to set.
    agent._learn_config = learn_config

    # Auto-memory / auto-learning need a LearnManager on the memory instance.
    # Only rebuild the backend when the bot itself injected the memory config: it
    # is the bot's own history dict, so merging learn in is non-destructive. A
    # user-supplied ``memory=`` (a live instance, ``memory=True``, a provider
    # string, or a dict) is never rewritten — rewriting it would change the
    # operator's chosen backend/intent. For those, the periodic nudge still
    # fires (it only needs ``_learn_config``) and drives the auto-injected
    # ``store_learning`` tool, so persona/preferences are still persisted; we
    # just don't silently swap their memory instance out from under them.
    if memory_was_injected:
        try:
            current = getattr(agent, "memory", None)
            mem_dict = dict(current) if isinstance(current, dict) else {"history": True, "history_limit": 20}
            mem_dict["learn"] = learn_config.to_dict() if hasattr(learn_config, "to_dict") else learn_config
            user_id = getattr(agent, "user_id", None)
            if hasattr(agent, "_init_memory"):
                agent._init_memory(mem_dict, user_id=user_id)
            # A bot-injected history dict resolves ``_auto_memory`` to the
            # framework default (None/False), not an explicit opt-out, so turn
            # it on — a LearnManager without auto-extraction would be inert.
            if not getattr(agent, "_auto_memory", None):
                agent._auto_memory = True
        except Exception as e:  # pragma: no cover - defensive
            logger.debug(f"Bot: could not rebuild memory for learning: {e}")
    else:
        logger.debug("Bot: enabled nudge cadence (user memory left intact)")

    logger.debug(f"Bot: session learning enabled for agent '{getattr(agent, 'name', '?')}'")


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


def _coerce_shell_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "on")
    if value is None:
        return default
    return bool(value)


def _gateway_bind_host(config: Optional[Any]) -> Optional[str]:
    if config is None:
        return None
    for attr in ("bind_host", "host"):
        host = getattr(config, attr, None)
        # ``GatewayServer.host`` is a method/property accessor — call it before
        # stringifying, otherwise ``is_loopback`` sees a repr and misclassifies
        # a genuinely loopback deployment as exposed.
        if callable(host):
            try:
                host = host()
            except Exception:  # pragma: no cover - defensive
                host = None
        if host:
            return str(host)
    return None


def _shell_auto_approve_is_safe(
    config: Optional[Any],
    ch_cfg: Dict[str, Any],
    bind_host: Optional[str] = None,
) -> bool:
    """Blanket shell auto-approve is only safe on a loopback bind + non-group surface.

    Mirrors the auth token's exposure-aware posture (``assert_external_bind_safe``):
    an externally-bound gateway or a multi-user/group channel must not silently
    grant RCE to every sender. Returns ``True`` only when the gateway binds to a
    loopback interface AND the channel is not a multi-user/group surface.

    ``bind_host`` is the gateway's resolved bind interface, passed explicitly by
    the gateway (which holds it on its own server config, not on the per-channel
    ``BotConfig``). When it is unknown we fall back to any host attribute on
    ``config``; a truly absent host means "no gateway" (the local ``Bot()``
    wrapper on a loopback process), which is safe.
    """
    bind_host = bind_host or _gateway_bind_host(config)
    if bind_host is not None:
        try:
            from praisonaiagents.gateway.protocols import is_loopback

            if not is_loopback(bind_host):
                return False
        except ImportError:  # pragma: no cover - core always present in-tree
            # Unknown exposure — fail closed on the highest-blast-radius path.
            return False

    group_policy = str(ch_cfg.get("group_policy") or "").strip().lower()
    if group_policy:
        # Every configured group policy — including ``command_only`` — is a
        # multi-user surface where any group member's message can reach the
        # shell, so blanket auto-approval must be downgraded to approval.
        return False

    return True


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
    gateway_bind_host: Optional[str] = None,
) -> Any:
    """Opt-in shell execution for inbound channel bots (Slack, Telegram, etc.).

    ``gateway_bind_host`` is the interface the gateway actually bound to. The
    per-channel ``config`` (a ``BotConfig``) does not carry it, so the gateway
    passes its resolved bind host explicitly; without it an externally-bound
    gateway would be invisible to the exposure-aware auto-approve downgrade.
    """
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

    # Inject the stdout-reporting directive unless it is already present.
    # Guard on the full directive (via a stable marker phrase) rather than the
    # bare tool name so preconfigured agents whose own system prompt already
    # mentions ``execute_command`` still receive the "report stdout verbatim"
    # instruction — otherwise the model keeps replying "there was no output".
    instructions = getattr(agent, "instructions", "") or ""
    if "include the command's stdout verbatim" not in instructions.lower():
        agent.instructions = (
            instructions
            + "\n\nYou can run shell commands on the bot server using the execute_command "
            "tool. When a user asks you to run a command, actually call execute_command "
            "and report its output back: include the command's stdout verbatim in your "
            "reply. Do not claim there was no output when the tool returned stdout."
        ).strip()

    deny = set(getattr(agent, "_perm_deny", None) or frozenset())
    deny -= _SHELL_TOOL_NAMES
    agent._perm_deny = frozenset(deny)

    auto_approve = _coerce_shell_bool(ch_cfg.get("auto_approve_shell", True), default=True)

    # Exposure-aware downgrade: blanket auto-approval silently grants RCE to every
    # sender on an externally-bound or multi-user/group surface. Only keep it where
    # it is safe (loopback bind + non-group), unless the operator explicitly
    # acknowledges the exposure — the same "calibrated by exposure" posture the
    # gateway auth token already enforces via assert_external_bind_safe.
    if auto_approve and not _shell_auto_approve_is_safe(config, ch_cfg, gateway_bind_host):
        acknowledged = _coerce_shell_bool(
            ch_cfg.get("auto_approve_shell_acknowledge_exposed", False)
        )
        if not acknowledged:
            logger.warning(
                "Channel %r enables shell on an exposed/multi-user surface; "
                "downgrading auto_approve_shell to require approval. Set "
                "auto_approve_shell_acknowledge_exposed: true to keep blanket "
                "auto-approval.",
                channel_type or "?",
            )
            auto_approve = False

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