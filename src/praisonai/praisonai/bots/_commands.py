"""
Shared chat command utilities for PraisonAI bots.

DRY: format_status() and format_help() are used identically across
Telegram, Discord, and Slack bots.  Keep them in one place.
"""

from __future__ import annotations

import logging
import time
from typing import Callable, Dict, Optional, Set, TYPE_CHECKING, Any

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from praisonaiagents import Agent
    from ._run_control import SessionRunControl


class CommandAccessPolicy:
    """Manages per-command access control for bot commands."""
    
    ALWAYS_ALLOWED = frozenset({"help", "whoami"})

    # Privileged, state-changing commands that default to admin-only whenever a
    # policy is configured (admin_users and/or user_allowed_commands set). They
    # remain available to everyone when no policy is configured, so this stays
    # backward-compatible. /learn reads host sources and authors skills that
    # alter future agent behaviour, so it belongs here.
    PRIVILEGED_COMMANDS = frozenset({"learn"})
    
    def __init__(
        self, 
        admin_users: Optional[Set[str]] = None,
        user_allowed_commands: Optional[Set[str]] = None
    ):
        """Initialize command access policy.
        
        Args:
            admin_users: Set of user IDs who can run any command
            user_allowed_commands: Set of commands regular users can run.
                None means all commands allowed (backward compatibility)
        """
        self.admin_users = admin_users or set()
        self.user_allowed_commands = user_allowed_commands

    @property
    def is_configured(self) -> bool:
        """Whether any access restriction has been configured.

        When False the policy is permissive (legacy behaviour); when True the
        privileged-command guard applies.
        """
        return bool(self.admin_users) or self.user_allowed_commands is not None
    
    def can_run(self, user_id: str, command: str) -> bool:
        """Check if user can run a specific command.
        
        Args:
            user_id: User identifier
            command: Command name (without prefix)
            
        Returns:
            True if user can run the command
        """
        # Admins can run any command
        if user_id in self.admin_users:
            return True
        
        # Always-allowed commands are available to everyone
        if command in self.ALWAYS_ALLOWED:
            return True

        # Privileged commands are admin-only once any policy is configured.
        # (Admins were already allowed above.) With no policy configured we
        # fall through to the permissive default below for backward compat.
        if command in self.PRIVILEGED_COMMANDS and self.is_configured:
            if self.user_allowed_commands is not None:
                return command in self.user_allowed_commands
            return False
        
        # If no restrictions, all commands are allowed
        if self.user_allowed_commands is None:
            return True
        
        # Check if command is in user's allowed list
        return command in self.user_allowed_commands
    
    def get_allowed_commands(self, user_id: str, all_commands: Set[str]) -> Set[str]:
        """Get list of commands a user is allowed to run.
        
        Args:
            user_id: User identifier
            all_commands: Set of all available commands
            
        Returns:
            Set of command names the user can run
        """
        if user_id in self.admin_users:
            return all_commands
        
        if self.user_allowed_commands is None:
            if not self.is_configured:
                return all_commands
            # admin_users configured but no per-user allow list: everything
            # except privileged commands is available to regular users.
            return all_commands - self.PRIVILEGED_COMMANDS
        
        return self.ALWAYS_ALLOWED | (self.user_allowed_commands & all_commands)


class CommandRegistry:
    """Unified command registry for all bot adapters."""
    
    def __init__(self):
        """Initialize the command registry."""
        self._commands: Dict[str, Dict[str, Any]] = {}
        self._initialize_builtin_commands()
    
    def _initialize_builtin_commands(self):
        """Register built-in commands."""
        self.register("help", {"description": "Show help message", "builtin": True})
        self.register("status", {"description": "Show bot status", "builtin": True})
        self.register("new", {"description": "Reset conversation session", "builtin": True})
        self.register("stop", {"description": "Cancel current agent task", "builtin": True})
        self.register("whoami", {"description": "Show your user info and permissions", "builtin": True})
        self.register("sethome", {"description": "Set this chat as the home channel for scheduled deliveries", "builtin": True})
        # New runtime control commands
        self.register("model", {"description": "Switch LLM model for this session", "builtin": True})
        self.register("usage", {"description": "Show token usage and estimated cost", "builtin": True})
        self.register("compress", {"description": "Compress conversation to free context window", "builtin": True})
        self.register("queue", {"description": "Queue a follow-up message", "builtin": True})
        # Learn a grounded skill from sources (codebase, docs, PDFs, or this chat)
        self.register("learn", {"description": "Learn a reusable skill from sources you describe (e.g. /learn deploy steps from this repo)", "builtin": True})
    
    def register(
        self, 
        command: str, 
        metadata: Optional[Dict[str, Any]] = None,
        handler: Optional[Callable] = None
    ) -> None:
        """Register a command.
        
        Args:
            command: Command name (without prefix)
            metadata: Command metadata (description, category, etc.)
            handler: Optional command handler function
        """
        if metadata is None:
            metadata = {}
        
        self._commands[command] = {
            "handler": handler,
            **metadata
        }
    
    def unregister(self, command: str) -> bool:
        """Unregister a command.
        
        Args:
            command: Command name to unregister
            
        Returns:
            True if command was unregistered, False if not found or builtin
        """
        if command in self._commands and not self._commands[command].get("builtin"):
            del self._commands[command]
            return True
        return False
    
    def get_command(self, command: str) -> Optional[Dict[str, Any]]:
        """Get command metadata and handler.
        
        Args:
            command: Command name
            
        Returns:
            Command metadata dict or None if not found
        """
        return self._commands.get(command)
    
    def get_all_commands(self) -> Dict[str, Dict[str, Any]]:
        """Get all registered commands.
        
        Returns:
            Dict of command name -> metadata
        """
        return self._commands.copy()
    
    def get_command_names(self) -> Set[str]:
        """Get set of all command names.
        
        Returns:
            Set of command names
        """
        return set(self._commands.keys())
    
    def format_help(
        self, 
        user_id: str,
        policy: Optional[CommandAccessPolicy] = None,
        agent: Optional["Agent"] = None,
        platform: str = "unknown"
    ) -> str:
        """Format help message showing available commands.
        
        Args:
            user_id: User requesting help
            policy: Access policy to filter commands
            agent: Current agent
            platform: Platform name
            
        Returns:
            Formatted help text
        """
        if policy:
            allowed = policy.get_allowed_commands(user_id, self.get_command_names())
        else:
            allowed = self.get_command_names()
        
        agent_name = agent.name if agent else "No agent"
        model = getattr(agent, "llm", "default") if agent else "default"
        
        lines = ["Available Commands"]
        
        # Sort commands for consistent display
        for cmd in sorted(allowed):
            cmd_info = self._commands.get(cmd, {})
            desc = cmd_info.get("description", "No description")
            lines.append(f"/{cmd} - {desc}")
        
        lines.append(f"\nAgent: {agent_name}")
        lines.append(f"Model: {model}")
        
        return "\n".join(lines)
    
    def format_whoami(
        self,
        user_id: str,
        username: Optional[str] = None,
        policy: Optional[CommandAccessPolicy] = None
    ) -> str:
        """Format whoami response showing user info and permissions.
        
        Args:
            user_id: User identifier
            username: User's display name
            policy: Access policy for permissions check
            
        Returns:
            Formatted whoami text
        """
        lines = ["User Information"]
        lines.append(f"User ID: {user_id}")
        
        if username:
            lines.append(f"Username: {username}")
        
        if policy:
            if user_id in policy.admin_users:
                lines.append("Role: Admin (all commands available)")
            else:
                lines.append("Role: User")
                allowed = policy.get_allowed_commands(user_id, self.get_command_names())
                lines.append(f"Allowed commands: {', '.join(sorted(allowed))}")
        else:
            lines.append("Role: User (no restrictions)")
        
        return "\n".join(lines)


# Global command registry instance
_global_registry = CommandRegistry()


def get_command_registry() -> CommandRegistry:
    """Get the global command registry instance.
    
    Returns:
        The global CommandRegistry instance
    """
    return _global_registry


def build_command_access_policy(config: Any) -> CommandAccessPolicy:
    """Build a :class:`CommandAccessPolicy` from a bot config.

    Shared by all adapters (Telegram, Slack, Discord) so per-command
    authorization is expressed consistently across channels. Reads the optional
    ``admin_users`` and ``user_allowed_commands`` attributes (comma-separated
    strings) from ``config``; when neither is set the policy is permissive,
    preserving legacy behaviour.

    Args:
        config: Bot configuration object.

    Returns:
        A configured CommandAccessPolicy.
    """
    admin_users: Set[str] = set()
    admin_raw = getattr(config, "admin_users", None)
    if admin_raw:
        admin_users = {u.strip() for u in str(admin_raw).split(",") if u.strip()}

    user_allowed_commands: Optional[Set[str]] = None
    allowed_raw = getattr(config, "user_allowed_commands", None)
    if allowed_raw is not None:
        # An explicitly empty string is a deliberate "allow no extra commands"
        # allow-list (still configured), distinct from None (unset/permissive).
        user_allowed_commands = {
            c.strip() for c in str(allowed_raw).split(",") if c.strip()
        }

    return CommandAccessPolicy(
        admin_users=admin_users,
        user_allowed_commands=user_allowed_commands,
    )


def format_status(
    agent: Optional["Agent"],
    platform: str,
    started_at: Optional[float],
    is_running: bool,
) -> str:
    """Format a /status response string.

    Args:
        agent: The bot's agent (may be None).
        platform: Platform name (telegram, discord, slack).
        started_at: Epoch timestamp when bot started (None if not started).
        is_running: Whether the bot is currently running.
    """
    agent_name = agent.name if agent else "No agent"
    model = getattr(agent, "llm", "default") if agent else "default"
    uptime = ""
    if started_at:
        elapsed = int(time.time() - started_at)
        hours, remainder = divmod(elapsed, 3600)
        minutes, seconds = divmod(remainder, 60)
        uptime = f"{hours}h {minutes}m {seconds}s"
    return (
        f"Bot Status\n"
        f"Agent: {agent_name}\n"
        f"Model: {model}\n"
        f"Platform: {platform}\n"
        f"Uptime: {uptime}\n"
        f"Running: {is_running}"
    )


def format_help(
    agent: Optional["Agent"],
    platform: str,
    extra_commands: Optional[Dict[str, str]] = None,
) -> str:
    """Format a /help response string.

    Args:
        agent: The bot's agent (may be None).
        platform: Platform name.
        extra_commands: Dict of command_name -> description for custom commands.
    """
    agent_name = agent.name if agent else "No agent"
    model = getattr(agent, "llm", "default") if agent else "default"
    lines = [
        "Available Commands",
        "/status - Show bot status and info",
        "/new - Reset conversation session",
        "/stop - Cancel current agent task",
        "/help - Show this help message",
    ]
    if extra_commands:
        for cmd, desc in extra_commands.items():
            lines.append(f"/{cmd} - {desc}")
    lines.append(f"\nAgent: {agent_name}")
    lines.append(f"Model: {model}")
    return "\n".join(lines)


def handle_stop_command(session_manager, user_id: str) -> str:
    """Handle a /stop command to cancel an active run.
    
    This function works with both the legacy BotSessionManager approach
    and the newer SessionRunControl approach for maximum compatibility.
    
    Args:
        session_manager: BotSessionManager instance or SessionRunControl
        user_id: User ID to cancel run for
        
    Returns:
        Response message indicating success or failure
    """
    # Handle SessionRunControl (newer approach)
    if hasattr(session_manager, 'stop'):
        try:
            import asyncio
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # We're in an async context, need to use create_task
                task = asyncio.create_task(session_manager.stop(user_id))
                # This is a synchronous function, so we can't await
                # Return a message indicating async operation is happening
                return "⏳ Cancellation requested..."
            else:
                # No event loop, run synchronously
                stopped = asyncio.run(session_manager.stop(user_id))
                if stopped:
                    return "✅ Current task cancelled. Send a new message to start fresh."
                else:
                    return "ℹ️ No active task to cancel."
        except Exception as e:
            return f"❌ Error stopping task: {e}"
    
    # Handle BotSessionManager (legacy approach)
    elif hasattr(session_manager, 'cancel_run'):
        was_cancelled = session_manager.cancel_run(user_id, "user_stop_command")
        if was_cancelled:
            return "✅ Current task cancelled. Send a new message to start fresh."
        else:
            return "ℹ️ No active task to cancel."
    
    else:
        return "❌ Stop command not available (run control not enabled)"


async def handle_stop_command_async(
    user_id: str,
    run_control: Optional["SessionRunControl"] = None,
) -> str:
    """Async version of handle_stop_command for SessionRunControl.
    
    Args:
        user_id: User identifier
        run_control: SessionRunControl instance for managing runs
        
    Returns:
        Response message to send to user
    """
    if run_control is None:
        return "❌ Stop command not available (run control not enabled)"
        
    try:
        stopped = await run_control.stop(user_id)
        if stopped:
            return "✅ Current task cancelled. Send a new message to start fresh."
        else:
            return "ℹ️ No active task to cancel."
    except Exception as e:
        return f"❌ Error stopping task: {e}"


def handle_run_status_command(
    user_id: str,
    run_control: Optional["SessionRunControl"] = None,
) -> str:
    """Handle request for current run status.
    
    Args:
        user_id: User identifier
        run_control: SessionRunControl instance
        
    Returns:
        Status message
    """
    if run_control is None:
        return "Run control not enabled"
        
    try:
        status = run_control.get_run_status(user_id)
        
        if not status["is_running"]:
            pending_info = " (has queued message)" if status["has_pending"] else ""
            return f"💤 No active task{pending_info}"
            
        elapsed = status.get("elapsed_seconds", 0)
        elapsed_str = f"{elapsed//60}m {elapsed%60}s" if elapsed > 60 else f"{elapsed}s"
        
        pending_info = ""
        if status["has_pending"]:
            preview = status.get("pending_preview", "")
            pending_info = f"\n📝 Queued: {preview}"
            
        return f"⚡ Task running for {elapsed_str}{pending_info}"
    except Exception as e:
        return f"Error getting status: {e}"


def handle_model_command(
    session_manager,
    user_id: str,
    model_name: Optional[str] = None,
    agent: Optional["Agent"] = None,
) -> str:
    """Handle /model command for runtime model switching.
    
    Args:
        session_manager: BotSessionManager instance
        user_id: User ID
        model_name: Optional model name to switch to
        agent: Current agent instance
        
    Returns:
        Response message
    """
    # Resolve the storage key so the override is keyed identically to how
    # chat() looks it up (handles cross-platform identity resolution).
    storage_key = user_id
    if hasattr(session_manager, '_storage_key'):
        try:
            storage_key = session_manager._storage_key(user_id)
        except Exception:
            storage_key = user_id

    if not model_name:
        # Show current model — prefer the per-user override if one is set,
        # otherwise fall back to the agent's configured model.
        overrides = getattr(session_manager, '_model_overrides', {})
        current = overrides.get(storage_key)
        if not current and agent and hasattr(agent, 'llm'):
            current = agent.llm if isinstance(agent.llm, str) else "default"
        if not current:
            return "No model configured. Use /model <name> to set one."
        return f"Current model: {current}\nUse /model <name> to switch (e.g., /model gpt-4o)"

    # Store the override per user. chat() applies it inside the per-agent lock
    # and restores the original afterwards, so the shared Agent instance is
    # never mutated for other concurrent users.
    if not hasattr(session_manager, '_model_overrides'):
        session_manager._model_overrides = {}
    session_manager._model_overrides[storage_key] = model_name

    return f"✅ Model switched to {model_name} for this conversation."


def handle_usage_command(
    session_manager,
    user_id: str,
    agent: Optional["Agent"] = None,
) -> str:
    """Handle /usage command to show token usage and cost.
    
    Args:
        session_manager: BotSessionManager instance  
        user_id: User ID
        agent: Current agent instance
        
    Returns:
        Response message with usage info
    """
    # Check for usage tracking via hooks or session metadata
    usage_info = {}
    
    # Try to get usage from session metadata if tracked
    if hasattr(session_manager, '_usage_tracker'):
        usage_info = session_manager._usage_tracker.get(user_id, {})
    
    # Check agent's token tracking if available
    if agent and hasattr(agent, 'get_token_usage'):
        try:
            agent_usage = agent.get_token_usage()
            usage_info.update(agent_usage)
        except Exception:
            pass
    
    # Format usage response
    if not usage_info:
        return "No usage data available. Usage tracking may not be enabled."
    
    total_tokens = usage_info.get('total_tokens', 0)
    prompt_tokens = usage_info.get('prompt_tokens', 0)
    completion_tokens = usage_info.get('completion_tokens', 0)
    
    # Estimate cost (rough estimates, would need model-specific pricing)
    cost_estimate = total_tokens * 0.00002  # Default estimate
    
    lines = [
        "📊 Token Usage",
        f"Total: {total_tokens:,} tokens",
    ]
    
    if prompt_tokens or completion_tokens:
        lines.append(f"Prompt: {prompt_tokens:,} | Completion: {completion_tokens:,}")
    
    lines.append(f"Est. cost: ${cost_estimate:.4f}")
    
    return "\n".join(lines)


def handle_compress_command(
    session_manager,
    user_id: str,
    agent: Optional["Agent"] = None,
) -> str:
    """Handle /compress command for context window management.
    
    Args:
        session_manager: BotSessionManager instance
        user_id: User ID  
        agent: Current agent instance
        
    Returns:
        Response message
    """
    try:
        # Get user's chat history
        if not hasattr(session_manager, '_histories'):
            return "❌ No conversation history to compress."
        
        storage_key = user_id
        if hasattr(session_manager, '_storage_key'):
            storage_key = session_manager._storage_key(user_id)
        
        history = session_manager._histories.get(storage_key, [])
        if len(history) < 10:
            return "ℹ️ Conversation too short to compress (need at least 10 messages)."
        
        # Import optimizer
        try:
            from praisonaiagents.context.optimizer import SummarizeOptimizer
            from praisonaiagents.context.tokens import estimate_messages_tokens
        except ImportError:
            # Fallback to simple truncation
            original_len = len(history)
            # Keep system messages and last 5 exchanges
            system_msgs = [m for m in history if m.get("role") == "system"]
            other_msgs = [m for m in history if m.get("role") != "system"]
            compressed = system_msgs + other_msgs[-10:]  # Keep last 5 exchanges (10 messages)
            
            session_manager._histories[storage_key] = compressed
            removed = original_len - len(compressed)
            
            return f"✅ Compressed conversation: removed {removed} older messages."
        
        # Use SummarizeOptimizer if available
        original_tokens = estimate_messages_tokens(history)
        optimizer = SummarizeOptimizer(preserve_recent=10)
        
        # Target 50% reduction
        target_tokens = original_tokens // 2
        compressed_history, result = optimizer.optimize(history, target_tokens)
        
        # Update history
        session_manager._histories[storage_key] = compressed_history
        
        # Persist if store available
        if hasattr(session_manager, '_store') and session_manager._store:
            try:
                session_manager._persist(storage_key)
            except Exception:
                pass
        
        tokens_saved = result.tokens_saved if hasattr(result, 'tokens_saved') else 0
        messages_removed = len(history) - len(compressed_history)
        
        return f"✅ Compressed {messages_removed} messages, freed ~{tokens_saved:,} tokens."
        
    except Exception as e:
        logger.error(f"Compression failed: {e}")
        return f"❌ Compression failed: {e}"


def handle_queue_command(
    session_manager,
    user_id: str,
    message_text: Optional[str] = None,
    run_control: Optional["SessionRunControl"] = None,
) -> str:
    """Handle /queue command for message queuing.

    Delegates to the canonical :class:`SessionRunControl` pending slot, which
    is the only mechanism that is actually drained by the gateway run loop
    (``chat_with_run_control`` calls ``next_pending``/``finish_run``). A
    message is only meaningful to queue while a run is in flight; if the bot
    is idle there is nothing to run "after", so the user is told to just send
    the message normally instead of being given a false promise.

    Args:
        session_manager: BotSessionManager instance
        user_id: User ID
        message_text: Optional message to queue
        run_control: SessionRunControl instance (falls back to
            ``session_manager._run_control`` when not supplied)

    Returns:
        Response message
    """
    # Resolve run control from the explicit arg or the session manager.
    if run_control is None:
        run_control = getattr(session_manager, "_run_control", None)

    if run_control is None:
        return (
            "ℹ️ Message queuing isn't enabled for this bot. "
            "Just send your message and it will be processed."
        )

    if not message_text:
        # Show whether a follow-up is currently pending for this user.
        try:
            status = run_control.get_run_status(user_id)
        except Exception:
            status = {}
        if status.get("has_pending"):
            preview = status.get("pending_preview", "")
            return f"📝 Pending follow-up: {preview}"
        return "No follow-up queued. Use /queue <message> to add one while a task is running."

    # Submit through run control so the message is parked in the pending slot
    # that the run loop actually drains after the current turn completes.
    import asyncio

    from ._run_control import RunDecision

    async def _submit() -> "RunDecision":
        return await run_control.submit(user_id, message_text)

    try:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop is not None and loop.is_running():
            # Schedule on the running loop; we can't block-await from here.
            loop.create_task(_submit())
            return "⏳ Follow-up noted — it will run after the current task completes."

        decision = asyncio.run(_submit())
    except Exception as e:  # noqa: BLE001 - surface a friendly message
        return f"❌ Could not queue message: {e}"

    if decision == RunDecision.RUN_NOW:
        return (
            "ℹ️ No task is currently running, so there's nothing to queue behind. "
            "Send your message normally to run it now."
        )
    if decision == RunDecision.MERGED:
        return "⏳ Added to your pending follow-up — it will run after the current task completes."
    if decision == RunDecision.STEERED:
        return "🧭 Injected into the running task as live guidance."
    return "⏳ Follow-up queued — it will run after the current task completes."


def handle_learn_command(
    agent: Optional["Agent"],
    request: Optional[str] = None,
) -> str:
    """Handle /learn command to author a grounded skill from sources.

    Drives :meth:`Agent.learn_skill`, which gathers the named sources with the
    agent's existing tools and authors one grounded SKILL.md via ``skill_manage``.

    Args:
        agent: The bot's agent (must support ``learn_skill``/``learn``).
        request: Description of the sources to learn from and the skill to
            produce, e.g. "deploy steps from this repo and the runbook PDF".

    Returns:
        Response message with the authored skill summary, or guidance.
    """
    if agent is None:
        return "❌ Learn is not available (no agent configured)."

    if not request or not request.strip():
        return (
            "ℹ️ Usage: /learn <sources and skill to make>\n"
            "Example: /learn deploy steps from this repo and the runbook PDF"
        )

    learn_fn = getattr(agent, "learn_skill", None) or getattr(agent, "learn", None)
    if not callable(learn_fn):
        return "❌ This agent does not support learning skills from sources."

    try:
        result = learn_fn(request.strip())
        return str(result) if result else "✅ Skill authored."
    except Exception as e:  # noqa: BLE001 - surface a friendly message
        return f"❌ Could not learn skill: {e}"
