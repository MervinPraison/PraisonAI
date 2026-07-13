"""
Shared chat command utilities for PraisonAI bots.

DRY: format_status() and format_help() are used identically across
Telegram, Discord, and Slack bots.  Keep them in one place.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Callable, Dict, List, Optional, Set, TYPE_CHECKING, Any

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from praisonaiagents import Agent
    from ._run_control import SessionRunControl

logger = logging.getLogger(__name__)


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
        # Conversation-control primitives surfacing existing core capabilities
        self.register("undo", {"description": "Undo the last turn's file changes", "builtin": True})
        self.register("sessions", {"description": "List recent saved sessions/checkpoints", "builtin": True})
        self.register("resume", {"description": "Resume a saved session: /resume <id>", "builtin": True})
        self.register("retry", {"description": "Retry your last message", "builtin": True})
        self.register("reasoning", {"description": "Toggle whether extended-thinking output is shown", "builtin": True})
        # Consent-first automation suggestions & blueprints (accept/dismiss in chat)
        self.register("automations", {"description": "List and accept/dismiss suggested automations", "builtin": True})
        self.register("blueprint", {"description": "Create an automation from a template: /blueprint <name> [slot=value ...]", "builtin": True})
    
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
    
    def menu_entries(
        self,
        platform: str = "unknown",
        policy: Optional[CommandAccessPolicy] = None,
        user_id: Optional[str] = None,
        extra_commands: Optional[Dict[str, str]] = None,
    ) -> List[tuple]:
        """Return ``(name, description)`` pairs for native command-menu registration.

        This is the single source of truth adapters project into a platform's
        native command menu (Telegram ``set_my_commands``, Discord application
        commands, Slack subcommands). Entries are policy-filtered so a caller
        only ever sees the commands they are permitted to run.

        Args:
            platform: Platform name (informational; menus are the same today
                across platforms but the argument allows future per-platform
                filtering).
            policy: Optional access policy used to filter the visible commands.
                When ``None`` all commands are returned (legacy permissive).
            user_id: The user the menu is being built for. Required for
                per-user policy filtering; when ``None`` an unrestricted menu
                is returned.
            extra_commands: Optional ``{name: description}`` map of adapter-
                registered custom commands to include alongside the built-ins.

        Returns:
            A list of ``(name, description)`` tuples sorted by command name.
        """
        all_names = self.get_command_names()
        if extra_commands:
            all_names = all_names | set(extra_commands.keys())

        if policy is not None and user_id is not None:
            allowed = policy.get_allowed_commands(user_id, all_names)
        else:
            allowed = all_names

        entries: List[tuple] = []
        for name in sorted(allowed):
            cmd_info = self._commands.get(name)
            if cmd_info is not None:
                desc = cmd_info.get("description", "No description")
            elif extra_commands and name in extra_commands:
                desc = extra_commands[name] or "Custom command"
            else:
                desc = "No description"
            entries.append((name, desc))
        return entries

    async def dispatch(
        self,
        name: str,
        *args,
        **kwargs,
    ) -> Any:
        """Invoke a registered command's handler, if one is bound.

        Adapters may route through this instead of maintaining a local
        name→handler chain. Built-in commands only expose a handler when one
        was bound via :meth:`register`; when a command has no handler this
        returns ``None`` so the caller can fall back to its own handling.

        Args:
            name: Command name (without the leading ``/``).
            *args: Positional arguments forwarded to the handler.
            **kwargs: Keyword arguments forwarded to the handler.

        Returns:
            The handler's result, or ``None`` when the command is unknown or
            has no bound handler.
        """
        cmd_info = self._commands.get(name)
        if not cmd_info:
            return None
        handler = cmd_info.get("handler")
        if handler is None:
            return None

        result = handler(*args, **kwargs)
        if asyncio.iscoroutine(result):
            result = await result
        return result

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


def _newest_py_mtime_ns(checkout_dir: str) -> int:
    """Return the newest ``.py`` modification time (ns) under ``checkout_dir``.

    Returns ``0`` when no readable ``.py`` files are found. Best-effort: per-file
    ``OSError`` and any walk error are swallowed so the caller can fail open.
    """
    import os

    newest = 0
    try:
        for root, _dirs, files in os.walk(checkout_dir):
            for name in files:
                if not name.endswith(".py"):
                    continue
                try:
                    mtime = os.stat(os.path.join(root, name)).st_mtime_ns
                except OSError:
                    continue
                if mtime > newest:
                    newest = mtime
    except Exception:
        return 0
    return newest


def _fingerprint_dir(checkout_dir: Optional[str]) -> Optional[str]:
    """Best-effort fingerprint of a single directory (git rev + newest mtime).

    * when ``checkout_dir`` is a git checkout, ``git rev-parse HEAD`` is used and
      the newest source ``.py`` mtime is *combined* with it
      (``"<rev>+mtime:<int_ns>"``) so an in-place file overwrite that does **not**
      advance ``HEAD`` (e.g. an editable/source checkout patched by ``pip install
      -U`` or a manual copy) still moves the fingerprint;
    * otherwise the newest source ``.py`` mtime alone is used as
      ``"mtime:<int_ns>"`` so an in-place file update still moves the
      fingerprint, preserving nanosecond precision for rapid edits;
    * on any error (no git, unreadable dir) ``None`` is returned so callers
      fail open and never block normal operation.
    """
    if not isinstance(checkout_dir, str) or not checkout_dir:
        return None

    # Prefer a git revision when the checkout is a working tree.
    rev = None
    try:
        import subprocess

        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=checkout_dir,
            capture_output=True,
            text=True,
            timeout=5,
        )
        candidate = result.stdout.strip()
        if result.returncode == 0 and candidate:
            rev = candidate
    except Exception:
        rev = None

    # Compute the newest .py mtime so an in-place edit registers even when git
    # succeeds but HEAD is unchanged (dirty/source checkout). Use nanosecond
    # precision so rapid successive edits are distinguishable.
    newest = _newest_py_mtime_ns(checkout_dir)

    if rev is not None:
        # Combine so a same-HEAD file overwrite still moves the fingerprint.
        if newest > 0:
            return f"{rev}+mtime:{newest}"
        return rev

    if newest > 0:
        return f"mtime:{newest}"

    return None


def read_code_fingerprint(checkout_dir: Optional[str] = None) -> Optional[str]:
    """Return a lightweight fingerprint of the on-disk gateway code.

    The gateway is a long-lived process that imports much of its surface
    lazily. When an operator updates a *running* checkout in place (``git
    pull`` / ``pip install -U`` / an auto-update step on a durable volume) the
    next first-use lazy import can pick up changed code and fail cryptically.
    Capturing this fingerprint once at boot and comparing it before a hot
    operation lets the gateway refuse the risky operation with a clear
    "restart required" message instead of crashing.

    This is the concrete, wrapper-side implementation (subprocess + filesystem
    walk); the pure comparison predicate lives in the core SDK as
    :func:`praisonaiagents.gateway.detect_code_skew`.

    When ``checkout_dir`` is not given, the fingerprint spans **both** packages
    that participate in the hot ``/model`` path: the ``praisonai`` wrapper
    (which owns the command handler) and the ``praisonaiagents`` SDK (whose
    ``gateway.*`` surface is lazy-imported). In an installed layout these are
    sibling packages, so an in-place update to *either* must move the
    fingerprint. The per-package fingerprints are combined fail-open: any
    package that resolves contributes; if none resolve, ``None`` is returned.

    Args:
        checkout_dir: Directory whose code revision to fingerprint. When given,
            only that directory is fingerprinted. When omitted, both the
            ``praisonai`` and ``praisonaiagents`` package directories are used.

    Returns:
        An opaque, non-secret fingerprint string, or ``None`` if it cannot be
        determined.
    """
    import os

    if checkout_dir is not None:
        return _fingerprint_dir(checkout_dir)

    # Fingerprint both packages on the hot path so an in-place update to either
    # the wrapper or the lazily-imported SDK is detected. Resolve each package
    # directory independently and fail open per package.
    targets = []
    try:
        # praisonai/praisonai/ — the wrapper package that owns the /model path.
        targets.append(
            ("praisonai", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        )
    except Exception:
        pass
    try:
        import praisonaiagents

        agents_file = getattr(praisonaiagents, "__file__", None)
        if agents_file:
            targets.append(
                ("praisonaiagents", os.path.dirname(os.path.abspath(agents_file)))
            )
    except Exception:
        pass

    parts = []
    for label, directory in targets:
        fp = _fingerprint_dir(directory)
        if fp:
            parts.append(f"{label}={fp}")

    if not parts:
        return None
    return "|".join(parts)


def capture_boot_fingerprint(session_manager) -> Optional[str]:
    """Capture and cache the wrapper code fingerprint at gateway startup.

    Call this once when the long-lived gateway/bot process boots (before any
    hot operation can run) so :func:`check_code_skew` has a true baseline taken
    at startup rather than on first ``/model`` use. It is idempotent: a
    previously captured fingerprint is preserved.

    Best-effort and fail-open: returns ``None`` (and stores nothing) on any
    error so startup is never blocked. (Issue #2460)

    Args:
        session_manager: The bot/gateway session manager to cache the
            fingerprint on (``_boot_code_fp``).

    Returns:
        The captured fingerprint, or ``None`` if it could not be determined.
    """
    try:
        if session_manager is None:
            return None
        # Pre-resolve the pure comparison predicate now, while imports are
        # known-good. Caching it means check_code_skew never has to import the
        # SDK gateway surface *during* a hot operation — an in-place update that
        # broke that import would otherwise make the guard's own import raise,
        # fail open, and let the risky switch proceed (defeating the guard).
        try:
            if getattr(session_manager, "_boot_detect_code_skew", None) is None:
                from praisonaiagents.gateway import detect_code_skew

                session_manager._boot_detect_code_skew = detect_code_skew
        except Exception:
            pass
        existing = getattr(session_manager, "_boot_code_fp", None)
        if existing is not None:
            return existing
        boot_fp = read_code_fingerprint()
        try:
            session_manager._boot_code_fp = boot_fp
        except Exception:
            pass
        return boot_fp
    except Exception:
        return None


def check_code_skew(session_manager) -> Optional[str]:
    """Return a "restart required" message if the gateway code changed on disk.

    The gateway is a long-lived process that imports much of its surface
    lazily. When an operator updates a *running* checkout in place, the next
    first-use lazy import on a hot path (e.g. ``/model``) can pick up changed
    code and crash with a cryptic ``ImportError``. This best-effort guard
    compares the boot fingerprint (ideally captured at startup via
    :func:`capture_boot_fingerprint`) to the current on-disk fingerprint before
    such an operation. If no boot fingerprint was captured at startup it falls
    back to capturing one on first use.

    It is fail-open: any error, an unavailable fingerprint, or an explicit
    ``code_skew_guard = False`` opt-out returns ``None`` so normal operation is
    never blocked. (Issue #2460)

    Args:
        session_manager: The bot/gateway session manager. Used to cache the
            boot fingerprint and read an optional ``code_skew_guard`` toggle.

    Returns:
        A clear, actionable message string on detected skew, otherwise ``None``.
    """
    try:
        if session_manager is None:
            return None
        if getattr(session_manager, "code_skew_guard", True) is False:
            return None

        # Prefer the predicate resolved at boot (when imports were known-good)
        # so a broken SDK gateway surface after an in-place update cannot make
        # the guard's *own* import raise and fail open. Fall back to a fresh
        # import only when no boot reference was cached.
        detect_code_skew = getattr(session_manager, "_boot_detect_code_skew", None)
        if detect_code_skew is None:
            from praisonaiagents.gateway import detect_code_skew

        boot_fp = getattr(session_manager, "_boot_code_fp", None)
        if boot_fp is None:
            # No startup baseline was captured: capture it now as a fallback so
            # later in-place updates are still caught. Capturing at startup via
            # capture_boot_fingerprint() additionally guards the very first call.
            capture_boot_fingerprint(session_manager)
            return None

        disk_fp = read_code_fingerprint()
        skew = detect_code_skew(boot_fp, disk_fp)
        if skew:
            return (
                f"⚠️ Gateway code changed on disk since it started "
                f"({skew[0]} → {skew[1]}). Restart the gateway to apply "
                f"updates before switching models."
            )
    except Exception:
        # Never let the guard itself break a hot operation.
        return None
    return None


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
    # Pre-flight code-skew guard: if the gateway's code changed on disk since
    # it booted, refuse the switch with a clear "restart required" message
    # instead of risking a cryptic ImportError from a first-use lazy import.
    if model_name:
        skew_message = check_code_skew(session_manager)
        if skew_message:
            return skew_message

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


def handle_undo_command(
    agent: Optional["Agent"],
) -> str:
    """Handle /undo to rewind the last turn's file changes.

    Surfaces the existing core primitive :meth:`Agent.undo`, which restores
    files to the state before the last autonomous iteration. Available only
    when the agent tracks changes (``autonomy`` with ``track_changes``); the
    handler degrades gracefully otherwise.

    Args:
        agent: The bot's agent (may be None).

    Returns:
        Response message indicating whether anything was reverted.
    """
    if agent is None:
        return "❌ Undo is not available (no agent configured)."

    undo_fn = getattr(agent, "undo", None)
    if not callable(undo_fn):
        return "❌ This agent does not support undo (change tracking not enabled)."

    try:
        reverted = undo_fn()
    except Exception as e:  # noqa: BLE001 - surface a friendly message
        return f"❌ Could not undo: {e}"

    return "✅ Reverted the last turn." if reverted else "ℹ️ Nothing to undo."


def handle_sessions_command(
    session_manager,
    user_id: str,
) -> str:
    """Handle /sessions to list recent saved sessions.

    Lists the conversation sessions the gateway is currently tracking so a
    user can pick one to ``/resume``. Falls back gracefully when the session
    manager does not expose session keys.

    Args:
        session_manager: BotSessionManager instance.
        user_id: User ID requesting the listing.

    Returns:
        A formatted list of session identifiers, or guidance.
    """
    # Scope every lookup to the requesting user's storage key so one user can
    # never enumerate another user's sessions (the in-memory `_histories` map
    # is a *shared* dict keyed by per-user storage key).
    storage_key = user_id
    if hasattr(session_manager, "_storage_key"):
        try:
            storage_key = session_manager._storage_key(user_id)
        except Exception:
            storage_key = user_id

    keys: List[str] = []
    list_fn = getattr(session_manager, "list_sessions", None)
    if callable(list_fn):
        try:
            # Prefer a user-scoped contract when the manager supports it;
            # fall back to an unfiltered call only if the signature rejects it.
            try:
                keys = list(list_fn(user_id))
            except TypeError:
                keys = list(list_fn())
        except Exception:
            keys = []
    elif hasattr(session_manager, "_histories"):
        try:
            # Only surface the caller's own session, never other users' keys.
            if storage_key in session_manager._histories:
                keys = [storage_key]
        except Exception:
            keys = []

    if not keys:
        return "No saved sessions yet."

    lines = ["📁 Recent sessions:"]
    for key in keys[:50]:
        lines.append(f"• {key}")
    lines.append("\nUse /resume <id> to switch to one.")
    return "\n".join(lines)


def handle_resume_command(
    session_manager,
    user_id: str,
    session_id: Optional[str] = None,
) -> str:
    """Handle /resume to switch to a previously saved session.

    Args:
        session_manager: BotSessionManager instance.
        user_id: User ID issuing the command.
        session_id: Identifier of the session to resume.

    Returns:
        Response message confirming the resume, or usage guidance.
    """
    if not session_id or not session_id.strip():
        return "ℹ️ Usage: /resume <id>  (see /sessions for the list)"

    session_id = session_id.strip()

    resume_fn = getattr(session_manager, "resume_session", None)
    if callable(resume_fn):
        try:
            ok = resume_fn(user_id, session_id)
        except Exception as e:  # noqa: BLE001
            return f"❌ Could not resume session: {e}"
        return (
            f"✅ Resumed session {session_id}."
            if ok
            else f"❌ Session {session_id} not found."
        )

    # No resume_session() primitive on this manager. Be honest: we can confirm
    # whether a session exists, but we cannot switch the active conversation to
    # it, so we must not claim the resume succeeded.
    if hasattr(session_manager, "_histories"):
        if session_id in session_manager._histories:
            return (
                "ℹ️ This bot can see saved sessions, but switching to a "
                "different one isn't supported here (no resume primitive)."
            )
        return f"❌ Session {session_id} not found. Use /sessions to list them."

    return "❌ Resuming sessions isn't supported by this bot."


def get_last_user_message(
    session_manager,
    user_id: str,
) -> Optional[str]:
    """Return the most recent non-empty user message for *user_id*, or None.

    Adapters use this to actually re-dispatch the prior turn through the normal
    conversation path (``session.chat(...)``) so ``/retry`` re-runs the message
    instead of merely echoing it.

    Args:
        session_manager: BotSessionManager instance.
        user_id: User ID issuing the command.

    Returns:
        The previous user message text, or ``None`` if there is nothing to retry.
    """
    storage_key = user_id
    if hasattr(session_manager, "_storage_key"):
        try:
            storage_key = session_manager._storage_key(user_id)
        except Exception:
            storage_key = user_id

    history: List[Dict[str, Any]] = []
    if hasattr(session_manager, "_histories"):
        history = session_manager._histories.get(storage_key, []) or []

    for msg in reversed(history):
        if msg.get("role") == "user":
            content = msg.get("content")
            if isinstance(content, str) and content.strip():
                return content
    return None


def handle_retry_command(
    session_manager,
    user_id: str,
) -> str:
    """Handle /retry to re-run the user's last message.

    Looks up the most recent user turn so the caller can re-submit it. Adapters
    should call :func:`get_last_user_message` and re-dispatch the returned text
    through their normal ``session.chat(...)`` path; this helper returns a
    user-facing acknowledgement (or guidance when there's nothing to retry).

    Args:
        session_manager: BotSessionManager instance.
        user_id: User ID issuing the command.

    Returns:
        A short acknowledgement, or guidance when there's nothing to retry.
    """
    last_user_msg = get_last_user_message(session_manager, user_id)

    if not last_user_msg:
        return "ℹ️ Nothing to retry — no previous message found."

    return f"🔁 Retrying your last message:\n{last_user_msg}"


# Tracks per-user reasoning-visibility preferences for /reasoning. Stored on
# the session manager when available so it survives alongside other per-user
# state; falls back to this module-level map otherwise.
_reasoning_visibility: Dict[str, bool] = {}


def handle_reasoning_command(
    session_manager,
    user_id: str,
    agent: Optional["Agent"] = None,
) -> str:
    """Handle /reasoning to toggle extended-thinking visibility.

    Toggles whether extended-thinking ("reasoning") output is shown to the
    user for this conversation. The preference is stored per user on the
    session manager when possible so the gateway can consult it when rendering
    responses.

    Args:
        session_manager: BotSessionManager instance.
        user_id: User ID issuing the command.
        agent: Current agent instance (optional).

    Returns:
        Response message reflecting the new visibility state.
    """
    storage_key = user_id
    if hasattr(session_manager, "_storage_key"):
        try:
            storage_key = session_manager._storage_key(user_id)
        except Exception:
            storage_key = user_id

    store = getattr(session_manager, "_reasoning_visibility", None)
    if store is None:
        if session_manager is not None and not hasattr(
            session_manager, "_reasoning_visibility"
        ):
            try:
                session_manager._reasoning_visibility = {}
                store = session_manager._reasoning_visibility
            except Exception:
                store = _reasoning_visibility
        else:
            store = _reasoning_visibility

    current = store.get(storage_key, False)
    new_state = not current
    store[storage_key] = new_state

    return (
        "🧠 Reasoning output will be shown for this conversation."
        if new_state
        else "🙈 Reasoning output will be hidden for this conversation."
    )


def is_reasoning_visible(session_manager, user_id: str) -> bool:
    """Return the current /reasoning visibility preference for *user_id*.

    Response-rendering code can consult this to decide whether to include
    extended-thinking output. Defaults to ``False`` (hidden) when no
    preference has been set.

    Args:
        session_manager: BotSessionManager instance.
        user_id: User ID whose preference to read.

    Returns:
        ``True`` if reasoning output should be shown, else ``False``.
    """
    storage_key = user_id
    if hasattr(session_manager, "_storage_key"):
        try:
            storage_key = session_manager._storage_key(user_id)
        except Exception:
            storage_key = user_id

    store = getattr(session_manager, "_reasoning_visibility", None)
    if not isinstance(store, dict):
        store = _reasoning_visibility
    return bool(store.get(storage_key, False))
