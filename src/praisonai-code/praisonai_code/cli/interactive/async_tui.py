"""
PraisonAI Async TUI Application.

Full-screen terminal UI with:
- Non-blocking LLM execution (UI stays responsive)
- Scrollable output area with keyboard navigation
- Fixed bottom input pane (always visible)
- Activity indicators during processing

Key fixes:
- Uses threading for LLM calls to prevent UI freeze
- Uses Buffer + BufferControl for scrollable output
- Proper app.invalidate() for UI refresh
"""

import logging
import os
import shlex
import shutil
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional
from datetime import datetime

# ============================================================================
# Debug Logging - Only enabled with --debug flag or PRAISON_DEBUG=1
# ============================================================================

logger = logging.getLogger(__name__)
_debug_initialized = False

# Sentinel marking a failed registry build so it is not retried every command.
_REGISTRY_FAILED = object()

def _init_debug_logging():
    """Initialize debug logging to file. Only called when debug mode is enabled."""
    global _debug_initialized
    if _debug_initialized:
        return
    
    _debug_log_file = os.path.expanduser("~/.praisonai/async_tui_debug.log")
    os.makedirs(os.path.dirname(_debug_log_file), exist_ok=True)
    
    _file_handler = logging.FileHandler(_debug_log_file, mode='a')
    _file_handler.setLevel(logging.DEBUG)
    _file_handler.setFormatter(logging.Formatter(
        '%(asctime)s - %(levelname)s - %(message)s'
    ))
    
    logger.setLevel(logging.DEBUG)
    logger.addHandler(_file_handler)
    _debug_initialized = True
    logger.debug("Debug logging initialized")

# Check if debug mode is enabled via environment variable
if os.environ.get("PRAISON_DEBUG", "").lower() in ("1", "true", "yes"):
    _init_debug_logging()

# ============================================================================
# Branding - Import from unified source
# ============================================================================

from praisonai_code.cli.branding import get_logo, get_version


class ReviewDiffError(RuntimeError):
    """Raised when the review diff could not be collected.

    Distinguishes a genuine collection failure (import/repo/Git error) from a
    successful-but-empty diff so the caller does not mislabel errors as a clean
    working tree.
    """


# ============================================================================
# Configuration
# ============================================================================

@dataclass
class AsyncTUIConfig:
    """Configuration for the Async TUI application."""
    model: str = "gpt-4o-mini"
    show_logo: bool = True
    show_status_bar: bool = True
    session_id: Optional[str] = None
    workspace: Optional[str] = None
    history_file: Optional[str] = None
    compact_mode: bool = False
    multiline_mode: bool = False
    autonomy_mode: bool = True  # Enable autonomous task delegation (aligned with InteractiveConfig)
    debug: bool = False  # Enable debug logging to file (~/.praisonai/async_tui_debug.log)
    no_rules: bool = False  # Disable auto-injection of project instruction files
    plan_mode: bool = False  # Read-only PLAN mode: deny writes/edits/shell until confirmed
    enable_acp: bool = True  # Load ACP tools + start the ACP runtime (disable via --no-acp)
    enable_lsp: bool = True  # Load LSP tools + start the LSP runtime (disable via --no-lsp)


# ============================================================================
# Auth / execution failure detection (issue #2562)
# ============================================================================

# Signatures that indicate an authentication / authorization failure. Kept in
# sync with praisonaiagents.llm.error_classifier ErrorCategory.AUTH patterns so
# both raised exceptions and logged-then-swallowed errors are detected.
_AUTH_ERROR_SIGNATURES = (
    "authentication failed",
    "invalid api key",
    "invalid_api_key",
    "incorrect api key",
    "authenticationerror",
    "http 401",
    "error code: 401",
    "error code: 403",
)


def _detect_auth_error(text: Optional[str]) -> Optional[str]:
    """Return a concise auth-error message if *text* looks like an auth failure."""
    if not text:
        return None
    lowered = text.lower()
    for sig in _AUTH_ERROR_SIGNATURES:
        if sig in lowered:
            return "Authentication failed: check your API key/credentials."
    return None


def _extract_response_output(response) -> Optional[str]:
    """Extract user-visible text from an agent response.

    Handles plain strings as well as wrapper objects such as
    ``AutonomyResult`` returned by ``agent.astart()`` which expose the
    generated text via an ``output`` attribute.
    """
    if response is None:
        return None
    output = getattr(response, "output", None)
    if output is not None:
        text = str(output).strip()
        return text or None
    text = str(response).strip()
    return text or None


def _is_empty_agent_response(response) -> bool:
    """True when the agent produced no user-visible output.

    ``agent.astart()`` may return a truthy wrapper object (e.g.
    ``AutonomyResult(success=True, output='')``) even on auth failure, so a
    plain ``not response`` check is insufficient (issue #2568).
    """
    return _extract_response_output(response) is None


class _LogCapture(logging.Handler):
    """Lightweight logging handler that records messages for failure detection."""

    def __init__(self, level: int = logging.WARNING):
        super().__init__(level=level)
        self.records: List[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self.records.append(record.getMessage())
        except Exception:
            pass

    def find_auth_error(self) -> Optional[str]:
        for message in self.records:
            found = _detect_auth_error(message)
            if found:
                return found
        return None


# ============================================================================
# Message Types
# ============================================================================

@dataclass
class ChatMessage:
    """A chat message."""
    role: str  # "user", "assistant", "system", "status"
    content: str
    timestamp: datetime = field(default_factory=datetime.now)


# ============================================================================
# Async TUI Application
# ============================================================================

class AsyncTUI:
    """
    Async TUI with non-blocking LLM execution and scrollable output.
    
    Key features:
    - Input box ALWAYS visible at bottom (never freezes)
    - Output scrolls above independently
    - LLM runs in background thread
    - UI stays responsive during processing
    """
    
    def __init__(self, config: Optional[AsyncTUIConfig] = None):
        self.config = config or AsyncTUIConfig()
        
        # Initialize debug logging if enabled
        if self.config.debug:
            _init_debug_logging()
        
        self.messages: List[ChatMessage] = []
        self._running = False
        self._agent = None
        self._review_agent = None  # Cached read-only agent for review commands
        self._interrupt_controller = None  # Cooperative cancellation for in-flight turns
        self._interrupt_worker = None  # Tracks an in-flight/abandoned turn worker
        self._processing = False
        self._status_text = ""
        self._last_error: Optional[Exception] = None
        self._app = None
        self._output_buffer = None
        self._prompt_queue: List[str] = []  # Queue for pending prompts
        # ids of queued prompts whose body is untrusted (skip @file expansion)
        self._no_mention_prompts: set = set()
        # ids of queued prompts that must run against the read-only review agent
        self._read_only_prompts: set = set()
        self._conversation_history: List[dict] = []  # Full conversation history
        self._total_tokens = 0
        self._total_cost = 0.0
        self._workspace_files: List[str] = []  # Files in workspace for @ completion
        self._runtime = None  # InteractiveRuntime for ACP/LSP
        self._runtime_started = False
        self._registry = None  # Unified command registry (lazy)
        self._checkpoints = None  # SessionCheckpointManager (lazy)
        self._checkpoints_ready = False
        self._prev_permission_mode = None  # Approval mode to restore when leaving PLAN
        # Sync PLAN indicator/toggle with a backend launched via --approval plan.
        self._sync_plan_mode_from_backend()
        
        # Terminal size
        self.term_width, self.term_height = shutil.get_terminal_size((80, 24))
        
        # Session ID
        import uuid
        self.session_id = self.config.session_id or str(uuid.uuid4())[:8]
        
        # Scan workspace for files
        self._scan_workspace()
    
    def _scan_workspace(self):
        """Scan workspace for files (for @ completion)."""
        import os
        workspace = self.config.workspace or os.getcwd()
        try:
            for root, dirs, files in os.walk(workspace):
                # Skip hidden directories
                dirs[:] = [d for d in dirs if not d.startswith('.')]
                for f in files:
                    if not f.startswith('.'):
                        rel_path = os.path.relpath(os.path.join(root, f), workspace)
                        self._workspace_files.append(rel_path)
                # Limit to 1000 files
                if len(self._workspace_files) >= 1000:
                    break
        except Exception:
            pass
    
    def _get_checkpoints(self):
        """Lazily build the coherent turn-checkpoint manager for this session.

        Binds ``SessionCheckpointManager`` to a view over the TUI's in-memory
        conversation history so ``/undo`` and ``/revert`` roll back **files and
        chat history together** on the default path — the same proven engine the
        legacy REPL uses. Enabled by default for interactive runs
        (``default=True``); opt out with ``checkpoints.auto: false`` or
        ``PRAISONAI_CHECKPOINTS=off``. Degrades to ``None`` on any failure so a
        checkpoint problem never breaks the TUI.
        """
        if self._checkpoints_ready:
            return self._checkpoints
        self._checkpoints_ready = True
        try:
            from praisonai_code.cli.interactive.repl import (
                _InMemoryConversationStore,
            )
            from praisonai_code.cli.features.session_checkpoints import (
                SessionCheckpointManager,
            )

            config = None
            try:
                from praisonai_code.cli.configuration.resolver import resolve_config

                config = resolve_config().extra
            except Exception:
                config = None

            store = _InMemoryConversationStore(
                self._conversation_history,
                agent_provider=lambda: self._agent,
            )
            mgr = SessionCheckpointManager.from_config(
                workspace_dir=(
                    os.environ.get("PRAISONAI_WORKSPACE")
                    or self.config.workspace
                    or os.getcwd()
                ),
                config=config,
                verbose=self.config.debug,
                session_store=store,
                session_id=self.session_id or "tui",
                default=True,
            )
            if mgr.enabled:
                mgr.checkpoint_turn("session start")
                self._checkpoints = mgr
        except Exception as exc:  # pragma: no cover - defensive
            logger.debug("Session checkpoints unavailable: %s", exc)
            self._checkpoints = None
        return self._checkpoints

    def _checkpoint_turn(self, label: str) -> None:
        """Record a pre-turn checkpoint so the revert timeline exists."""
        ckpt = self._get_checkpoints()
        if ckpt is not None:
            try:
                ckpt.checkpoint_turn(label)
            except Exception:  # pragma: no cover - never break a turn
                pass

    def _handle_undo(self) -> None:
        """/undo — roll files + conversation back to the previous turn."""
        ckpt = self._get_checkpoints()
        if ckpt is None or not getattr(ckpt, "enabled", False) or not ckpt.turns:
            self.messages.append(ChatMessage(role="system", content="Nothing to undo."))
            return
        ckpt.preview(1)
        restored = ckpt.revert(1)
        if restored:
            self.messages.append(ChatMessage(
                role="system",
                content=f"Undone last turn — files + conversation reverted to {restored.short_id}.",
            ))
        else:
            self.messages.append(ChatMessage(role="system", content="No checkpoint to undo."))

    def _handle_revert(self, args: str) -> None:
        """/revert [n] — roll files + conversation back n turns (default 1)."""
        ckpt = self._get_checkpoints()
        if ckpt is None or not getattr(ckpt, "enabled", False):
            self.messages.append(ChatMessage(
                role="system",
                content=(
                    "Checkpointing is disabled. Enable with checkpoints.auto: true "
                    "or PRAISONAI_CHECKPOINTS=on."
                ),
            ))
            return
        if not ckpt.turns:
            self.messages.append(ChatMessage(role="system", content="No checkpoints to revert to."))
            return
        n = 1
        token = str(args).strip().lower()
        if token and token != "last":
            try:
                n = int(token)
            except ValueError:
                self.messages.append(ChatMessage(role="system", content="Usage: /revert [n|last]"))
                return
        if n < 1 or n > len(ckpt.turns):
            self.messages.append(ChatMessage(
                role="system", content=f"Can only revert 1..{len(ckpt.turns)} turn(s).",
            ))
            return
        ckpt.preview(n)
        restored = ckpt.revert(n)
        if restored:
            self.messages.append(ChatMessage(
                role="system",
                content=f"Reverted {n} turn(s) — files + conversation restored to {restored.short_id}.",
            ))
        else:
            self.messages.append(ChatMessage(role="system", content="Failed to revert."))

    def _process_file_mentions(self, prompt: str) -> str:
        """Process @file mentions and include file contents."""
        import os
        import re
        
        workspace = self.config.workspace or os.getcwd()
        
        # Find all @file mentions
        pattern = r'@([^\s]+)'
        matches = re.findall(pattern, prompt)
        
        if not matches:
            return prompt
        
        file_contents = []
        for match in matches:
            file_path = os.path.join(workspace, match)
            if os.path.isfile(file_path):
                try:
                    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                        content = f.read()
                    file_contents.append(f"\n--- Content of {match} ---\n{content}\n--- End of {match} ---\n")
                except Exception as e:
                    file_contents.append(f"\n[Error reading {match}: {e}]\n")
        
        if file_contents:
            return prompt + "\n" + "\n".join(file_contents)
        return prompt
    
    # Tool names that can mutate the workspace or run commands. Review turns
    # run with these filtered OUT so a purported read-only review cannot write
    # files or execute commands even if the model attempts a write tool call.
    _WRITE_TOOL_NAMES = frozenset({
        "write_file", "edit_file", "apply_patch", "create_file", "delete_file",
        "move_file", "execute_command", "run_command", "shell", "bash",
    })

    def _get_agent(self, read_only: bool = False):
        """Lazy-load the agent with tools.

        When ``read_only`` is True a separate, cached agent is built whose tool
        set excludes write/command-execution tools (see ``_WRITE_TOOL_NAMES``),
        enforcing review commands at the capability level rather than by prompt
        instruction alone.
        """
        if read_only:
            if self._review_agent is None:
                self._review_agent = self._build_agent(read_only=True)
            return self._review_agent
        if self._agent is None:
            self._agent = self._build_agent(read_only=False)
        return self._agent

    def _build_agent(self, read_only: bool = False):
        """Construct an Agent, optionally with a read-only tool set."""
        logger.debug("Creating new agent (read_only=%s)...", read_only)
        try:
                from praisonaiagents import Agent
                
                # Load interactive tools (read_file, write_file, execute_command, etc.)
                tools = self._load_tools()
                if read_only and tools:
                    tools = [
                        t for t in tools
                        if getattr(t, "__name__", "") not in self._WRITE_TOOL_NAMES
                    ]
                logger.debug(f"Tools for agent: {len(tools) if tools else 0}")
                
                # Auto-inject project instruction files unless disabled
                instructions = "You are Praison AI, a helpful assistant. Be concise and helpful. You have access to tools for file operations, code execution, and web search."
                max_chars = 32000  # Default cap
                
                # Check config for rules settings with proper precedence
                try:
                    from praisonai_code.cli.configuration.loader import load_config
                    config = load_config()
                    if self.config.no_rules:
                        should_load_rules = False
                    else:
                        should_load_rules = config.rules.auto
                        max_chars = config.rules.max_chars
                except Exception:
                    # Config not available, use defaults
                    should_load_rules = not self.config.no_rules
                
                if should_load_rules:
                    try:
                        from praisonaiagents.memory import RulesManager
                        rules_manager = RulesManager(workspace_path=self.config.workspace or os.getcwd(), verbose=0)
                        rules_context = rules_manager.build_rules_context(max_chars=max_chars)
                        if rules_context:
                            instructions = f"{rules_context}\n\n{instructions}"
                            logger.debug("Project instruction files loaded")
                    except ImportError:
                        pass  # RulesManager not available
                    except Exception as e:
                        logger.debug(f"Error loading rules: {e}")

                # Build agent config
                agent_config = {
                    "name": "Praison",
                    "role": "AI Assistant", 
                    "goal": "Help the user with their requests",
                    "instructions": instructions,
                    "llm": self.config.model,
                    "tools": tools if tools else None,
                }
                
                # Enable autonomy for complex task handling when autonomy_mode is on
                if self.config.autonomy_mode:
                    agent_config["autonomy"] = True
                    logger.debug("Autonomy mode enabled")
                
                # Wire cooperative cancellation so Ctrl-C during a turn can stop
                # an in-flight generation / tool call at the next step boundary
                # while keeping the warm agent and session intact. Only the
                # primary agent owns the shared interrupt controller; the
                # read-only review agent reuses it so Ctrl-C still cancels.
                try:
                    from praisonaiagents.agent.interrupt import InterruptController
                    if not read_only or self._interrupt_controller is None:
                        controller = InterruptController()
                        if not read_only:
                            self._interrupt_controller = controller
                    else:
                        controller = self._interrupt_controller
                    agent_config["interrupt_controller"] = controller
                except ImportError:
                    if not read_only:
                        self._interrupt_controller = None

                logger.debug(f"Agent config: model={self.config.model}, tools={len(tools) if tools else 0}")
                agent = Agent(**agent_config)
                logger.debug("Agent created successfully")
                return agent
        except ImportError as e:
                logger.error(f"Failed to import praisonaiagents: {e}")
                raise RuntimeError(f"Failed to import praisonaiagents: {e}")
    
    async def _start_runtime(self):
        """Start the InteractiveRuntime with ACP/LSP servers."""
        if self._runtime_started:
            logger.debug("Runtime already started, skipping")
            return
        
        logger.debug("Starting runtime...")
        try:
            from praisonai_code.cli.features.interactive_runtime import create_runtime
            
            self._runtime = create_runtime(
                workspace=self.config.workspace or ".",
                lsp=self.config.enable_lsp,
                acp=self.config.enable_acp,
                approval="auto",  # Auto-approve for interactive mode
            )
            logger.debug("Runtime created")
            
            # Start runtime (this starts ACP/LSP servers)
            await self._runtime.start()
            self._runtime_started = True
            
            lsp_status = "ready" if self._runtime.lsp_ready else "failed"
            acp_status = "ready" if self._runtime.acp_ready else "failed"
            logger.debug(f"Runtime started: LSP={lsp_status}, ACP={acp_status}")
            
            # Return status
            return {
                "lsp": lsp_status,
                "acp": acp_status,
                "read_only": self._runtime.read_only
            }
        except ImportError as e:
            # Runtime not available, continue without it
            logger.debug(f"Runtime import error: {e}")
            self._runtime_started = True  # Mark as attempted
            return {"error": f"Runtime not available: {e}"}
        except Exception as e:
            logger.error(f"Runtime start error: {e}", exc_info=True)
            self._runtime_started = True
            return {"error": str(e)}
    
    def _load_tools(self):
        """Load interactive tools for the agent."""
        tools = []
        logger.debug("Starting tool loading...")
        
        # Load the requested interactive tool groups. ACP/LSP are on by default
        # but can be disabled (code --no-acp/--no-lsp) so an explicitly
        # restricted session never exposes the disabled capability.
        groups = ["basic"]
        if self.config.enable_acp:
            groups.append("acp")
        if self.config.enable_lsp:
            groups.append("lsp")
        try:
            from praisonai_code.cli.features.interactive_tools import get_interactive_tools
            tools = get_interactive_tools(
                groups=groups,
                workspace=self.config.workspace,
            )
            if tools:
                logger.debug(f"Loaded {len(tools)} tools from interactive_tools: {[t.__name__ for t in tools]}")
                return tools
        except ImportError as e:
            logger.debug(f"interactive_tools import failed: {e}")
        except Exception as e:
            logger.debug(f"interactive_tools error: {e}")
        
        # Fallback: try to load basic tools directly from praisonaiagents
        logger.debug("Falling back to direct praisonaiagents.tools import...")
        try:
            from praisonaiagents.tools import (
                read_file,
                write_file, 
                list_files,
                execute_command,
            )
            tools = [read_file, write_file, list_files, execute_command]
            logger.debug(f"Loaded basic tools: {[t.__name__ for t in tools]}")
        except ImportError as e:
            logger.debug(f"Basic tools import failed: {e}")
        
        # Try to add internet search
        try:
            from praisonaiagents.tools import internet_search
            tools.append(internet_search)
            logger.debug("Added internet_search tool")
        except ImportError as e:
            logger.debug(f"internet_search import failed: {e}")
        
        # Try to add schedule tools (default for all agents)
        try:
            from praisonaiagents.tools import schedule_add, schedule_list, schedule_remove
            tools.extend([schedule_add, schedule_list, schedule_remove])
            logger.debug("Added schedule tools: schedule_add, schedule_list, schedule_remove")
        except ImportError as e:
            logger.debug(f"Schedule tools import failed: {e}")
        
        logger.debug(f"Final tools loaded: {len(tools)}")
        return tools
    
    def _format_output(self) -> str:
        """Format all messages for the output pane."""
        lines = []
        
        # Logo - ALWAYS show at top (like Claude Code, OpenCode)
        if self.config.show_logo:
            logo = get_logo(self.term_width)
            lines.append(logo.strip())
            lines.append("")
            lines.append(f"  v{get_version()} · Model: {self.config.model}")
            lines.append("")
            # Only show tips if no conversation yet
            if not self.messages:
                lines.append("  Type your message and press Enter. Use /help for commands.")
                lines.append("  Use PageUp/PageDown or Ctrl+Up/Down to scroll.")
                lines.append("")
        
        # Messages
        for msg in self.messages:
            if msg.role == "user":
                lines.append(f"› {msg.content}")
                lines.append("")
            elif msg.role == "assistant":
                lines.append(f"● {msg.content}")
                lines.append("")
            elif msg.role == "system":
                lines.append(f"  {msg.content}")
                lines.append("")
            elif msg.role == "status":
                lines.append(f"  ⏳ {msg.content}")
                lines.append("")
            elif msg.role == "tool":
                lines.append(f"  ⚙ {msg.content}")
                lines.append("")
        
        # Processing indicator
        if self._processing:
            lines.append(f"  ⏳ {self._status_text}")
            lines.append("")
        
        return "\n".join(lines)
    
    def _update_output(self):
        """Update the output buffer and refresh UI."""
        if self._output_buffer:
            new_text = self._format_output()
            self._output_buffer.set_document(
                self._output_buffer.document.__class__(
                    text=new_text,
                    cursor_position=len(new_text)  # Cursor at end for auto-scroll
                ),
                bypass_readonly=True
            )
        if self._app:
            self._app.invalidate()

    def _get_live_backend(self):
        """Return the live interactive approval backend, or ``None``."""
        try:
            from praisonaiagents.approval import get_approval_registry
            return get_approval_registry().get_backend()
        except Exception:
            return None

    def _apply_permission_mode(self, mode) -> bool:
        """Switch the live approval backend into ``mode`` (e.g. PLAN).

        Reuses the already-shipped enforcement layer: the interactive backend's
        ``set_permission_mode`` makes PLAN unconditionally deny write/edit/
        delete/bash/shell. Returns ``True`` when a compatible backend accepted
        the mode so callers can honestly report enforcement status.
        """
        backend = self._get_live_backend()
        setter = getattr(backend, "set_permission_mode", None)
        if callable(setter):
            setter(mode)
            return True
        return False

    def _sync_plan_mode_from_backend(self) -> None:
        """Align ``config.plan_mode`` with the live backend on startup.

        When launched with ``--approval plan`` the backend already enforces
        PLAN; without this the ``[PLAN]`` indicator would be missing and the
        first no-arg ``/plan`` would *enable* an already-active mode instead of
        toggling it off (Greptile P1: startup unsynchronized).
        """
        try:
            from praisonaiagents.permissions import PermissionMode
        except Exception:
            return
        backend = self._get_live_backend()
        current = getattr(backend, "permission_mode", None)
        if current is not None:
            self.config.plan_mode = (current == PermissionMode.PLAN)

    def _set_plan_mode(self, enabled: bool) -> bool:
        """Enter/exit read-only PLAN mode, returning whether it is enforced.

        On exit we restore the mode the session launched with (e.g.
        ``accept-edits``/``bypass``) rather than blindly forcing DEFAULT, so a
        user who selected an approval policy keeps it (Greptile P1: plan exit
        must not discard the approval mode).
        """
        from praisonaiagents.permissions import PermissionMode
        if enabled:
            # Remember whatever mode is currently active so we can restore it.
            backend = self._get_live_backend()
            current = getattr(backend, "permission_mode", None)
            if current is not None and current != PermissionMode.PLAN:
                self._prev_permission_mode = current
            mode = PermissionMode.PLAN
        else:
            mode = getattr(self, "_prev_permission_mode", None) or PermissionMode.DEFAULT
            self._prev_permission_mode = None
        enforced = self._apply_permission_mode(mode)
        self.config.plan_mode = enabled
        if self._app:
            self._app.invalidate()
        return enforced

    # Built-in slash commands registered into the unified registry so /help
    # and autocomplete stay in lock-step with the dispatch branches below.
    _BUILTIN_COMMANDS = {
        "help": "Show this help",
        "exit": "Exit Praison AI",
        "quit": "Exit Praison AI",
        "clear": "Clear conversation",
        "new": "Start new conversation",
        "model": "Show or change model",
        "session": "Show current session info",
        "sessions": "List all saved sessions",
        "continue": "Continue most recent session",
        "history": "Show conversation history",
        "export": "Export conversation to file",
        "import": "Import conversation from file",
        "cost": "Show token usage and cost",
        "stats": "Show session statistics (model, tokens, cost)",
        "status": "Show ACP/LSP runtime status",
        "auto": "Toggle autonomy mode (auto-delegate complex tasks)",
        "debug": "Toggle debug logging",
        "plan": "Toggle read-only plan mode (/plan off to exit; /plan <task> to plan)",
        "code-review": "Review the uncommitted diff for bugs (read-only)",
        "security-review": "Audit the uncommitted diff for security issues (read-only)",
        "handoff": "Delegate to specialized agent (code/research/review/docs)",
        "compact": "Toggle compact output mode",
        "multiline": "Toggle multiline input mode",
        "files": "List workspace files for @ mentions",
        "queue": "Show pending prompts in queue",
        "undo": "Undo the last turn (files + conversation)",
        "revert": "Revert the last N turns (files + conversation)",
    }

    def _get_registry(self):
        """Lazily build the unified command registry (built-ins + custom).

        Custom ``.praisonai/commands/*.md`` commands become first-class
        ``/name`` entries here, driven from the same discovery that powers
        ``praisonai run --command``. Failures degrade to built-ins only.
        """
        if self._registry is None:
            try:
                from praisonai_code.cli.interactive.command_registry import (
                    create_default_registry,
                )

                self._registry = create_default_registry(
                    self._BUILTIN_COMMANDS, include_custom=True, include_skills=True
                )
            except Exception as exc:  # pragma: no cover - defensive
                logger.debug("Command registry unavailable: %s", exc)
                self._registry = _REGISTRY_FAILED
        if self._registry is _REGISTRY_FAILED:
            return None
        return self._registry

    def _replay_history(self, history, limit: int = 20) -> None:
        """Redraw a restored conversation as live chat messages.

        Reuses the same renderer that draws live turns so a resumed session
        shows prior user/assistant turns (and tool activity) exactly as they
        appeared, instead of only a one-line summary. Bounded to the last
        ``limit`` turns with a note about older turns.
        """
        if not history:
            return

        total = len(history)
        shown = history[-limit:] if limit and total > limit else history
        if total > len(shown):
            self.messages.append(ChatMessage(
                role="system",
                content=f"… {total - len(shown)} earlier turns",
            ))

        for msg in shown:
            role = msg.get("role", "assistant")
            content = msg.get("content", "")
            if role == "tool":
                role = "system"
            if not content:
                tool_calls = msg.get("tool_calls")
                if isinstance(tool_calls, list) and tool_calls:
                    names = ", ".join(
                        (tc.get("function", {}) or {}).get("name", "tool")
                        for tc in tool_calls
                        if isinstance(tc, dict)
                    )
                    content = f"[tool call] {names}" if names else "[tool call]"
                else:
                    continue
            self.messages.append(ChatMessage(role=role, content=content))

    def _handle_command(self, command: str) -> bool:
        """Handle slash commands. Returns True if handled."""
        parts = command.split(maxsplit=1)
        cmd = parts[0].lower().lstrip("/")
        args = parts[1] if len(parts) > 1 else ""
        
        if cmd in ("exit", "quit", "q"):
            self._running = False
            if self._app:
                self._app.exit()
            return True
        
        elif cmd == "help":
            help_text = """Available Commands:
  /help            Show this help
  /exit, /quit     Exit Praison AI
  /clear           Clear conversation
  /new             Start new conversation
  /model [name]    Show or change model
  /session         Show current session info
  /sessions        List all saved sessions
  /continue        Continue most recent session
  /history         Show conversation history
  /export [file]   Export conversation to file
  /import <file>   Import conversation from file
  /cost            Show token usage and cost
  /stats           Show session statistics (model, tokens, cost)
  /status          Show ACP/LSP runtime status
  /auto            Toggle autonomy mode (auto-delegate complex tasks)
  /debug           Toggle debug logging to ~/.praisonai/async_tui_debug.log
  /plan [task|off] Toggle read-only plan mode (/plan <task> plans; /plan off exits)
  /code-review [file|--staged]   Review the uncommitted diff for bugs (read-only)
  /security-review [file|--staged]  Audit the uncommitted diff for security issues (read-only)
  /handoff <type> <task>  Delegate to specialized agent (code/research/review/docs)
  /compact         Toggle compact output mode
  /multiline       Toggle multiline input mode
  /files           List workspace files for @ mentions
  /queue           Show pending prompts in queue
  /undo            Undo the last turn (files + conversation)
  /revert [n]      Revert the last N turns (files + conversation)

Keyboard Shortcuts:
  PageUp/Down      Scroll output
  Ctrl+Up/Down     Scroll output
  Ctrl+C           Clear input
  Ctrl+D           Exit (if input empty)
  Ctrl+Q           Exit

Tips:
  Use @filename to include file contents in your prompt
  Type multiple prompts while AI is thinking (queued)
  Use --debug flag or /debug command to enable debug logging"""
            registry = self._get_registry()
            if registry:
                custom = [
                    c for c in registry.list_commands()
                    if c.name not in self._BUILTIN_COMMANDS and c.kind.value != "builtin"
                ]
                if custom:
                    lines = ["", "Custom Commands:"]
                    for c in custom:
                        lines.append(f"  /{c.name:<14} {c.description}")
                    help_text += "\n" + "\n".join(lines)
            self.messages.append(ChatMessage(role="system", content=help_text))
            return True
        
        elif cmd == "clear":
            self.messages.clear()
            self._conversation_history.clear()
            self.messages.append(ChatMessage(role="system", content="Conversation cleared."))
            return True
        
        elif cmd == "new":
            self.messages.clear()
            self._conversation_history.clear()
            import uuid
            self.session_id = str(uuid.uuid4())[:8]
            self.messages.append(ChatMessage(role="system", content=f"New session: {self.session_id}"))
            return True
        
        elif cmd == "model":
            if args:
                self.config.model = args
                self._agent = None
                self._review_agent = None
                self.messages.append(ChatMessage(role="system", content=f"Model changed to: {args}"))
            else:
                self.messages.append(ChatMessage(role="system", content=f"Current model: {self.config.model}"))
            return True
        
        elif cmd == "session":
            info = f"Session: {self.session_id}\nModel: {self.config.model}\nMessages: {len(self._conversation_history)}"
            self.messages.append(ChatMessage(role="system", content=info))
            return True
        
        elif cmd == "history":
            if not self._conversation_history:
                self.messages.append(ChatMessage(role="system", content="No conversation history."))
            else:
                history_lines = []
                for i, msg in enumerate(self._conversation_history[-10:], 1):
                    role = msg.get("role", "unknown")
                    content = msg.get("content", "")[:80]
                    history_lines.append(f"{i}. [{role}] {content}...")
                self.messages.append(ChatMessage(role="system", content="\n".join(history_lines)))
            return True
        
        elif cmd == "export":
            filename = args or f"conversation_{self.session_id}.txt"
            try:
                with open(filename, "w") as f:
                    f.write("# Praison AI Conversation\n")
                    f.write(f"# Session: {self.session_id}\n")
                    f.write(f"# Model: {self.config.model}\n\n")
                    for msg in self._conversation_history:
                        f.write(f"[{msg.get('role', 'unknown')}]\n")
                        f.write(f"{msg.get('content', '')}\n\n")
                self.messages.append(ChatMessage(role="system", content=f"Exported to {filename}"))
            except Exception as e:
                self.messages.append(ChatMessage(role="system", content=f"Export failed: {e}"))
            return True
        
        elif cmd in ("cost", "stats"):
            stats_info = (
                f"Model:          {self.config.model}\n"
                f"Total tokens:   {self._total_tokens}\n"
                f"Estimated cost: ${self._total_cost:.4f}"
            )
            self.messages.append(ChatMessage(role="system", content=stats_info))
            return True
        
        elif cmd == "compact":
            self.config.compact_mode = not self.config.compact_mode
            mode = "enabled" if self.config.compact_mode else "disabled"
            self.messages.append(ChatMessage(role="system", content=f"Compact mode {mode}"))
            return True
        
        elif cmd == "multiline":
            self.config.multiline_mode = not self.config.multiline_mode
            mode = "enabled" if self.config.multiline_mode else "disabled"
            self.messages.append(ChatMessage(role="system", content=f"Multiline mode {mode}. Use Ctrl+D to submit."))
            return True
        
        elif cmd == "files":
            if not self._workspace_files:
                self.messages.append(ChatMessage(role="system", content="No files found in workspace."))
            else:
                files_list = self._workspace_files[:20]
                more = f"\n... and {len(self._workspace_files) - 20} more" if len(self._workspace_files) > 20 else ""
                self.messages.append(ChatMessage(role="system", content="Workspace files:\n" + "\n".join(f"  @{f}" for f in files_list) + more))
            return True
        
        elif cmd == "queue":
            if not self._prompt_queue:
                self.messages.append(ChatMessage(role="system", content="No prompts in queue."))
            else:
                queue_list = [f"{i+1}. {p[:50]}..." for i, p in enumerate(self._prompt_queue)]
                self.messages.append(ChatMessage(role="system", content="Queued prompts:\n" + "\n".join(queue_list)))
            return True
        
        elif cmd == "sessions":
            # List available sessions
            try:
                from praisonai_code.cli.session import get_session_store
                store = get_session_store()
                sessions = store.list_sessions()
                if not sessions:
                    self.messages.append(ChatMessage(role="system", content="No saved sessions found."))
                else:
                    lines = ["Available sessions:"]
                    for s in sessions[:10]:
                        sid = s.get("session_id", "unknown")
                        title = s.get("title", "Untitled")
                        lines.append(f"  {sid}: {title}")
                    if len(sessions) > 10:
                        lines.append(f"  ... and {len(sessions) - 10} more")
                    self.messages.append(ChatMessage(role="system", content="\n".join(lines)))
            except Exception as e:
                self.messages.append(ChatMessage(role="system", content=f"Could not list sessions: {e}"))
            return True
        
        elif cmd == "continue":
            # Continue most recent session
            try:
                from praisonai_code.cli.session import get_session_store
                store = get_session_store()
                sessions = store.list_sessions()
                if not sessions:
                    self.messages.append(ChatMessage(role="system", content="No sessions to continue."))
                else:
                    # Get most recent
                    sorted_sessions = sorted(
                        sessions,
                        key=lambda s: s.get("updated_at", s.get("created_at", 0)),
                        reverse=True
                    )
                    if sorted_sessions:
                        session = store.load(sorted_sessions[0].get("session_id"))
                        if session:
                            self.session_id = session.session_id
                            # Load the full stored history (not the default
                            # 50-message tail) so the replay's "… N earlier
                            # turns" note reflects the true total and older
                            # turns aren't silently dropped before bounding.
                            history = session.get_chat_history(
                                max_messages=max(session.message_count, 1)
                            )
                            self._conversation_history = history
                            # Reset the display so repeated /continue calls (or
                            # continuing after prior activity) redraw the
                            # restored conversation cleanly instead of appending
                            # to — and duplicating — stale on-screen turns.
                            self.messages.clear()
                            self.messages.append(ChatMessage(
                                role="system", 
                                content=f"Continued session: {self.session_id} ({len(history)} messages)"
                            ))
                            self._replay_history(history)
                        else:
                            self.messages.append(ChatMessage(role="system", content="Could not load session."))
            except Exception as e:
                self.messages.append(ChatMessage(role="system", content=f"Could not continue session: {e}"))
            return True
        
        elif cmd == "import":
            # Import session from file
            if not args:
                self.messages.append(ChatMessage(role="system", content="Usage: /import <filename>"))
            else:
                try:
                    import json
                    with open(args) as f:
                        data = json.load(f)
                    
                    # Load messages from file
                    messages = data.get("messages", [])
                    self._conversation_history = messages
                    self.session_id = data.get("session_id", self.session_id)
                    self.messages.append(ChatMessage(
                        role="system",
                        content=f"Imported {len(messages)} messages from {args}"
                    ))
                except FileNotFoundError:
                    self.messages.append(ChatMessage(role="system", content=f"File not found: {args}"))
                except Exception as e:
                    self.messages.append(ChatMessage(role="system", content=f"Import failed: {e}"))
            return True
        
        elif cmd == "status":
            # Show runtime status (ACP/LSP)
            if self._runtime:
                status = self._runtime.get_status()
                lsp = status.get("lsp", {})
                acp = status.get("acp", {})
                info = f"Runtime Status:\n  LSP: {lsp.get('status', 'unknown')}\n  ACP: {acp.get('status', 'unknown')}\n  Read-only: {status.get('read_only', False)}"
                self.messages.append(ChatMessage(role="system", content=info))
            else:
                self.messages.append(ChatMessage(role="system", content="Runtime not initialized."))
            return True
        
        elif cmd == "auto":
            # Toggle autonomy mode for complex task delegation
            self.config.autonomy_mode = not self.config.autonomy_mode
            mode = "enabled" if self.config.autonomy_mode else "disabled"
            self.messages.append(ChatMessage(
                role="system", 
                content=f"Autonomy mode {mode}. Agent will {'auto-delegate complex tasks' if self.config.autonomy_mode else 'handle tasks directly'}."
            ))
            # Recreate agent with autonomy setting
            self._agent = None
            self._review_agent = None
            return True
        
        elif cmd == "debug":
            # Toggle debug logging mode
            self.config.debug = not self.config.debug
            if self.config.debug:
                _init_debug_logging()
                logger.debug("Debug mode enabled via /debug command")
            mode = "enabled" if self.config.debug else "disabled"
            log_file = os.path.expanduser("~/.praisonai/async_tui_debug.log")
            self.messages.append(ChatMessage(
                role="system", 
                content=f"Debug mode {mode}. Logs written to: {log_file}"
            ))
            return True
        
        elif cmd == "plan":
            # Real plan mode: a persistent read-only permission mode enforced by
            # the approval backend (PLAN denies write/edit/delete/bash/shell),
            # not just a one-shot prompt. Reuses set_permission_mode so the very
            # next turn is actually blocked from mutating the workspace.
            sub = args.strip().lower() if args else ""
            if sub == "off":
                # Explicit exit — flip enforcement back to normal.
                self._set_plan_mode(False)
                self.messages.append(ChatMessage(
                    role="system",
                    content="Plan mode disabled. Writes/edits/commands are allowed again."
                ))
            elif not args:
                # Toggle: /plan with no args flips read-only mode on/off.
                enabled = not self.config.plan_mode
                enforced = self._set_plan_mode(enabled)
                if enabled:
                    note = (
                        "Plan mode enabled [PLAN] — read-only exploration. "
                        "Writes/edits/commands are denied until you /plan off."
                    )
                    if not enforced:
                        note += (
                            "\n(Note: no interactive approval backend is active, "
                            "so enforcement is advisory in this session.)"
                        )
                    self.messages.append(ChatMessage(role="system", content=note))
                else:
                    self.messages.append(ChatMessage(
                        role="system",
                        content="Plan mode disabled. Writes/edits/commands are allowed again."
                    ))
            else:
                # /plan <task>: enter read-only mode first, then ask the agent to
                # produce a plan. Enforcement means the plan step cannot mutate;
                # run /plan off (or approve) to execute afterwards.
                self._set_plan_mode(True)
                self.messages.append(ChatMessage(
                    role="system",
                    content=f"[PLAN] Creating plan (read-only) for: {args}\nRun /plan off to leave plan mode and execute."
                ))
                self._update_output()

                planning_prompt = f"""Create a detailed step-by-step plan for the following task. 
Do NOT execute anything yet, just analyze and plan.

Task: {args}

Provide:
1. Analysis of what needs to be done
2. Step-by-step plan with clear actions
3. Potential risks or considerations
4. Estimated complexity (simple/medium/complex)"""

                self._queue_or_execute(planning_prompt)
            return True

        elif cmd in ("code-review", "security-review"):
            # Review the uncommitted (or staged/per-file) diff using the shipped
            # read-only "review" agent preset. `security` swaps in a security
            # rubric; both attach the fenced diff so the reviewer sees the exact
            # changed lines. No writes are possible during review.
            security = cmd == "security-review"
            staged = False
            file_path = None
            usage = f"Usage: /{cmd} [file] [--staged] [--security]"
            try:
                tokens = shlex.split(args)
            except ValueError:
                # Malformed quoting (e.g. an unbalanced quote in a path).
                self.messages.append(ChatMessage(role="system", content=usage))
                return True
            for token in tokens:
                if token == "--staged":
                    staged = True
                elif token == "--security":
                    security = True
                elif not token.startswith("-"):
                    if file_path is not None:
                        # Only a single positional file path is supported.
                        self.messages.append(ChatMessage(role="system", content=usage))
                        return True
                    file_path = token

            try:
                prompt = self._build_review_prompt(
                    security=security, staged=staged, file_path=file_path
                )
            except ReviewDiffError as exc:
                self.messages.append(ChatMessage(
                    role="system",
                    content=f"Could not collect diff for review: {exc}",
                ))
                return True
            if prompt is None:
                self.messages.append(ChatMessage(
                    role="system",
                    content="Working tree clean — no uncommitted changes to review.",
                ))
                return True

            label = "security review" if security else "code review"
            self.messages.append(ChatMessage(
                role="system", content=f"🔍 Running {label} on the uncommitted diff..."
            ))
            self._update_output()
            # The prompt embeds an untrusted diff; skip @file expansion so a
            # `@../../secret` token inside the diff cannot exfiltrate files, and
            # run against the read-only review agent so write/exec tools are
            # unavailable regardless of what the model attempts.
            self._queue_or_execute(prompt, skip_file_mentions=True, read_only=True)
            return True

        elif cmd == "handoff":
            # Handoff to a specialized sub-agent
            if not args:
                self.messages.append(ChatMessage(
                    role="system",
                    content="""Usage: /handoff <agent_type> <task>
Available agent types:
  - code: Code analysis and generation
  - research: Web research and information gathering
  - review: Code review and quality analysis
  - docs: Documentation generation
Example: /handoff code "refactor the auth module" """
                ))
            else:
                parts = args.split(maxsplit=1)
                if len(parts) < 2:
                    self.messages.append(ChatMessage(role="system", content="Please specify both agent type and task."))
                else:
                    agent_type, task = parts
                    agent_type = agent_type.lower()
                    
                    # Map agent types to specialized prompts
                    agent_prompts = {
                        "code": f"You are a specialized code agent. Focus on code analysis, generation, and refactoring. Task: {task}",
                        "research": f"You are a research agent. Focus on gathering information and providing comprehensive analysis. Task: {task}",
                        "review": f"You are a code review agent. Focus on identifying issues, suggesting improvements, and ensuring quality. Task: {task}",
                        "docs": f"You are a documentation agent. Focus on creating clear, comprehensive documentation. Task: {task}",
                    }
                    
                    if agent_type in agent_prompts:
                        self.messages.append(ChatMessage(
                            role="system", 
                            content=f"🔄 Handing off to {agent_type} agent..."
                        ))
                        self._update_output()
                        self._queue_or_execute(agent_prompts[agent_type])
                    else:
                        self.messages.append(ChatMessage(
                            role="system",
                            content=f"Unknown agent type: {agent_type}. Use: code, research, review, or docs"
                        ))
            return True
        
        elif cmd == "undo":
            self._handle_undo()
            return True
        
        elif cmd == "revert":
            self._handle_revert(args)
            return True
        
        else:
            # Not a built-in: consult the unified command registry so custom
            # .praisonai/commands/*.md commands are first-class /name commands.
            registry = self._get_registry()
            resolved = registry.get(cmd) if registry else None
            if resolved is not None and resolved.handler is not None:
                try:
                    prompt = resolved.handler(args)
                except Exception as exc:
                    self.messages.append(ChatMessage(
                        role="system",
                        content=f"Command /{cmd} failed: {exc}",
                    ))
                    return True
                if prompt:
                    self.messages.append(ChatMessage(
                        role="system", content=f"Running /{cmd}..."
                    ))
                    self._update_output()
                    self._queue_or_execute(prompt)
                else:
                    self.messages.append(ChatMessage(
                        role="system",
                        content=f"Command /{cmd} produced no output.",
                    ))
                return True
            self.messages.append(ChatMessage(role="system", content=f"Unknown command: /{cmd}. Use /help for available commands."))
            return True
    
    def _execute_prompt(self, prompt: str, read_only: bool = False) -> Optional[str]:
        """Execute a prompt and return the response (suppresses agent output).

        ``read_only`` selects the review agent whose tool set excludes
        write/command-execution tools.
        """
        import sys
        import io
        import asyncio
        
        logger.debug(f"Executing prompt: {prompt[:100]}...")
        
        self._last_error = None
        try:
            agent = self._get_agent(read_only=read_only)
            logger.debug(f"Agent loaded: {agent.name if hasattr(agent, 'name') else 'unnamed'}")
            logger.debug(f"Agent tools: {[t.__name__ if hasattr(t, '__name__') else str(t) for t in (agent.tools or [])]}")
            
            # Capture agent's Rich output for logging
            old_stdout = sys.stdout
            old_stderr = sys.stderr
            captured_stdout = io.StringIO()
            captured_stderr = io.StringIO()
            sys.stdout = captured_stdout
            sys.stderr = captured_stderr

            # Capture WARNING/ERROR log records (e.g. "Authentication failed")
            # emitted by the agent so we can detect silent failures where
            # agent.start() logs an auth error but returns None.
            #
            # NOTE: praisonaiagents emits these via the *root* logger
            # (``logging.warning(...)`` in llm.py), so the handler must be on
            # the root logger to catch them. False positives are avoided by (a)
            # only matching precise auth signatures (no broad "permission
            # denied"/"access denied") and (b) gating on an empty response.
            log_capture = _LogCapture(level=logging.WARNING)
            root_logger = logging.getLogger()
            root_logger.addHandler(log_capture)
            
            try:
                # Try async execution first for better non-blocking behavior
                if hasattr(agent, 'astart'):
                    try:
                        # Share the process-wide async bridge instead of
                        # spawning a fresh loop per prompt, so LiteLLM/HTTPX/DB
                        # per-loop connection pools survive across turns and any
                        # caller-installed scoped_bridge() binding still wins.
                        # Wrapper-only optimisation; the except below falls back
                        # to plain sync execution when it is unavailable.
                        from praisonai_code._wrapper_bridge import import_wrapper_module
                        run_sync_or_offload = import_wrapper_module(
                            "praisonai._async_bridge"
                        ).run_sync_or_offload
                        response = run_sync_or_offload(
                            agent.astart(prompt),
                            thread_name="praisonai-tui-turn",
                        )
                        logger.debug("Used async execution (astart)")
                    except Exception as e:
                        logger.debug(f"Async execution failed: {e}, falling back to sync")
                        # Fallback to sync
                        response = agent.start(prompt)
                else:
                    response = agent.start(prompt)
                    logger.debug("Used sync execution (start)")
            finally:
                sys.stdout = old_stdout
                sys.stderr = old_stderr
                root_logger.removeHandler(log_capture)
                
                # Log captured output
                stdout_content = captured_stdout.getvalue()
                stderr_content = captured_stderr.getvalue()
                if stdout_content:
                    logger.debug(f"Agent stdout: {stdout_content[:500]}")
                if stderr_content:
                    logger.debug(f"Agent stderr: {stderr_content[:500]}")
            
            logger.debug(f"Response received: {str(response)[:200] if response else 'None'}")

            # Detect silent failures: some providers log an auth/permission
            # error and return None instead of raising. Surface these so the
            # CLI can exit with a non-zero status (issue #2562).
            #
            # NOTE: agent.astart() may return a truthy wrapper object such as
            # AutonomyResult(success=True, output='') even on auth failure, so
            # we must inspect the actual output rather than the object's
            # truthiness (issue #2568).
            output_text = _extract_response_output(response)
            auth_error = log_capture.find_auth_error()
            if auth_error and output_text is None:
                self._last_error = RuntimeError(auth_error)
                return f"Error: {auth_error}"

            # Surface explicit failures reported by wrapper objects even when
            # no auth signature matched (e.g. AutonomyResult.success is False).
            result_error = getattr(response, "error", None)
            if result_error:
                self._last_error = RuntimeError(str(result_error))
                return f"Error: {result_error}"
            if getattr(response, "success", None) is False:
                self._last_error = RuntimeError("Agent execution failed")
                # Preserve any partial/diagnostic output for the user instead
                # of hiding it behind a generic message (still exits non-zero
                # via ``execution_failed``).
                return output_text if output_text is not None else "Error: Agent execution failed"

            return output_text
        except Exception as e:
            logger.error(f"Error executing prompt: {e}", exc_info=True)
            self._last_error = e
            return f"Error: {e}"
    
    def _execute_prompt_interruptible(self, prompt: str) -> Optional[str]:
        """Run a turn while keeping the main thread responsive to Ctrl-C.

        The blocking ``_execute_prompt`` runs in a worker thread so the main
        thread can catch ``KeyboardInterrupt``. On Ctrl-C we request cooperative
        cancellation via the agent's ``InterruptController``; the core chat loop
        honours it at the next step boundary and returns the partial output,
        leaving the warm agent and session intact. Ensure the agent (and its
        controller) exist before the turn starts.
        """
        import threading

        self._get_agent()
        controller = self._interrupt_controller
        if controller is None:
            # No cooperative-cancellation primitive available: fall back to the
            # original blocking behaviour.
            return self._execute_prompt(prompt)

        # Guard against an abandoned prior worker (user pressed Ctrl-C twice and
        # started a new turn before the old daemon thread reached an interrupt
        # check). Clearing the shared controller here would un-cancel it and let
        # it resume concurrently against the warm session. If such a worker is
        # still alive, keep the cancellation request set and refuse to start a
        # new turn until it observes the interrupt and exits.
        prior = getattr(self, "_interrupt_worker", None)
        if prior is not None and prior.is_alive():
            print(
                "\n  ⏹ Previous turn is still cancelling; please wait a moment "
                "and try again."
            )
            return None

        controller.clear()
        result = {}

        def _worker():
            try:
                result["response"] = self._execute_prompt(prompt)
            except BaseException as exc:  # noqa: BLE001 - surface via _last_error
                self._last_error = exc
                result["response"] = None

        worker = threading.Thread(target=_worker, daemon=True)
        self._interrupt_worker = worker
        worker.start()

        interrupted = False
        while worker.is_alive():
            try:
                worker.join(timeout=0.1)
            except KeyboardInterrupt:
                if not interrupted:
                    interrupted = True
                    controller.request("user")
                    print("\n  ⏹ Interrupting… (finishing current step)")
                else:
                    # Second Ctrl-C: stop waiting; worker is daemon and the
                    # cooperative request has already been sent.
                    break

        if interrupted:
            self.messages.append(ChatMessage(
                role="system", content="Turn interrupted by user."
            ))

        return result.get("response")

    def _execute_in_background(
        self, prompt: str, skip_file_mentions: bool = False, read_only: bool = False
    ):
        """Execute prompt in background thread (non-blocking).

        ``skip_file_mentions`` bypasses ``@file`` expansion for prompts whose
        body is generated from untrusted content (e.g. a review diff), so a
        ``@../../secret`` token inside a diff cannot exfiltrate files.

        ``read_only`` routes the turn through a review agent whose tool set
        excludes write/command-execution tools, enforcing review commands at the
        capability level instead of by prompt instruction alone.
        """
        # Track tool calls for visibility
        tool_calls = []
        # Holds the live assistant message that streamed narrative is rendered
        # into as the turn progresses, plus the text seen so far (so a final
        # append can be skipped when the stream already surfaced the response).
        streamed = {"message": None, "text": ""}
        
        def tool_call_callback(message):
            """Callback triggered when a tool is called."""
            if "Calling function:" in message:
                parts = message.split("Calling function:")
                if len(parts) > 1:
                    tool_name = parts[1].strip()
                    if tool_name and tool_name not in tool_calls:
                        tool_calls.append(tool_name)
                        self._status_text = f"⚙ Using {tool_name}..."
                        self._update_output()
            elif "Function " in message and " returned:" in message:
                self._status_text = "Processing result..."
                self._update_output()

        def llm_content_callback(content=None, **_kwargs):
            """Render intermediate LLM narrative into the transcript live.

            The core emits ``llm_content`` with the full text of each LLM step
            as it completes, so a multi-step (tool-using) turn surfaces its
            narrative incrementally instead of only after the whole turn joins.
            Read-only review turns keep the spinner-only behaviour so their
            transcript stays a single summarised message.
            """
            if read_only or not content or not str(content).strip():
                return
            text = str(content).strip()
            msg = streamed["message"]
            if msg is None:
                msg = ChatMessage(role="assistant", content=text)
                streamed["message"] = msg
                self.messages.append(msg)
            elif text != msg.content:
                # A later step supersedes/extends the earlier narrative; show
                # the newest text rather than duplicating overlapping content.
                if text.startswith(msg.content):
                    msg.content = text
                else:
                    msg.content = f"{msg.content}\n\n{text}"
            streamed["text"] = msg.content
            self._update_output()
        
        # Register callbacks for tool visibility + live narrative. Save any
        # previously-registered callback per slot and restore it on cleanup
        # (rather than deleting the slot) so another in-process consumer that
        # owns these display slots keeps receiving events after our turn. Guard
        # every mutation with the core callbacks lock and an identity check,
        # mirroring praisonaiagents' own register/restore pattern.
        _sync_display_callbacks = None
        _callbacks_lock = None
        _registered_slots = {}
        _our_callbacks = {
            'tool_call': tool_call_callback,
            'llm_content': llm_content_callback,
        }
        try:
            from praisonaiagents import sync_display_callbacks
            from praisonaiagents.main import _callbacks_lock as _core_lock
            _sync_display_callbacks = sync_display_callbacks
            _callbacks_lock = _core_lock
            with _callbacks_lock:
                for _slot, _cb in _our_callbacks.items():
                    _registered_slots[_slot] = sync_display_callbacks.get(_slot)
                    sync_display_callbacks[_slot] = _cb
        except ImportError:
            pass
        
        def run():
            # Clear any stale cancellation request from a previous turn so a
            # fresh turn is not immediately interrupted.
            if self._interrupt_controller is not None:
                self._interrupt_controller.clear()
            self._processing = True
            self._status_text = "Praison AI is thinking..."
            self._update_output()
            
            # Process @file mentions (skipped for generated prompts whose body
            # is untrusted, e.g. a review diff, to prevent @file exfiltration).
            processed_prompt = (
                prompt if skip_file_mentions
                else self._process_file_mentions(prompt)
            )
            
            # Checkpoint files + conversation at the turn boundary before the
            # agent may mutate the workspace, so /undo and /revert can roll both
            # back together. Read-only turns (reviews) never mutate files, so
            # skip them to keep the revert timeline meaningful.
            if not read_only:
                self._checkpoint_turn(prompt[:60])
            
            # Add to conversation history
            self._conversation_history.append({"role": "user", "content": prompt})
            
            # Animate spinner while processing
            spinner = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
            start_time = time.time()
            
            # Start LLM execution in another thread
            result = [None]
            error = [None]
            done = [False]
            
            def execute_llm():
                try:
                    result[0] = self._execute_prompt(processed_prompt, read_only=read_only)
                except Exception as e:
                    error[0] = str(e)
                finally:
                    done[0] = True
            
            llm_thread = threading.Thread(target=execute_llm)
            llm_thread.start()
            
            # Update spinner while waiting
            idx = 0
            while not done[0]:
                elapsed = time.time() - start_time
                queue_info = f" | Queue: {len(self._prompt_queue)}" if self._prompt_queue else ""
                self._status_text = f"{spinner[idx]} Praison AI is thinking... ({elapsed:.1f}s){queue_info}"
                self._update_output()
                idx = (idx + 1) % len(spinner)
                time.sleep(0.1)
            
            llm_thread.join()
            
            # Restore the prior callback for each slot we owned. The identity
            # check ensures we only mutate a slot while it still holds our
            # callback, so a consumer that re-registered during the turn is
            # never clobbered; slots with no prior owner are removed.
            if _sync_display_callbacks is not None and _callbacks_lock is not None:
                with _callbacks_lock:
                    for _slot, _cb in _our_callbacks.items():
                        if _sync_display_callbacks.get(_slot) is _cb:
                            _prev = _registered_slots.get(_slot)
                            if _prev is not None:
                                _sync_display_callbacks[_slot] = _prev
                            else:
                                _sync_display_callbacks.pop(_slot, None)
            
            # Done processing current prompt
            self._processing = False
            self._status_text = ""
            
            # Show tool calls summary if any were made
            if tool_calls:
                tools_used = ", ".join(tool_calls)
                self.messages.append(ChatMessage(role="system", content=f"Tools used: {tools_used}"))
            
            streamed_msg = streamed["message"]
            if error[0]:
                self.messages.append(ChatMessage(role="assistant", content=f"Error: {error[0]}"))
                self._conversation_history.append({"role": "assistant", "content": f"Error: {error[0]}"})
            elif result[0]:
                # If the turn already streamed its narrative into a live
                # assistant message, reuse it as the finalised turn (updating it
                # in place if the full result differs) instead of appending a
                # duplicate. Otherwise append the result as before so /undo,
                # /revert and history are unaffected.
                if streamed_msg is not None:
                    if result[0] != streamed_msg.content:
                        streamed_msg.content = result[0]
                else:
                    self.messages.append(ChatMessage(role="assistant", content=result[0]))
                self._conversation_history.append({"role": "assistant", "content": result[0]})
            
            self._update_output()
            
            # Process next item in queue if any
            if self._prompt_queue:
                next_prompt = self._prompt_queue.pop(0)
                next_skip = id(next_prompt) in self._no_mention_prompts
                next_ro = id(next_prompt) in self._read_only_prompts
                self._no_mention_prompts.discard(id(next_prompt))
                self._read_only_prompts.discard(id(next_prompt))
                self.messages.append(ChatMessage(role="user", content=next_prompt))
                self._update_output()
                self._execute_in_background(
                    next_prompt, skip_file_mentions=next_skip, read_only=next_ro
                )
        
        # Run in background thread
        thread = threading.Thread(target=run, daemon=True)
        thread.start()
    
    def _build_review_prompt(
        self,
        security: bool = False,
        staged: bool = False,
        file_path: Optional[str] = None,
    ) -> Optional[str]:
        """Build a review prompt from the uncommitted diff.

        Collects the working-tree (or staged/per-file) diff via the shipped
        ``GitManager`` and wraps it in a review rubric fenced as ``diff`` so the
        read-only ``review`` agent preset can cite exact file:line locations.
        Returns ``None`` when the diff query succeeds but there is nothing to
        review, so the caller can report a clean working tree. Raises
        ``ReviewDiffError`` when the diff could not be collected (import,
        repository, or Git failure) so the caller can surface the real error
        instead of masking it as a clean tree.
        """
        try:
            from praisonai_code.cli.features.git_integration import GitManager

            git = GitManager(repo_path=self.config.workspace or None)
            diff = git.get_diff_content(staged=staged, file_path=file_path)
        except Exception as exc:
            logger.debug("Diff collection failed: %s", exc)
            raise ReviewDiffError(str(exc)) from exc

        if not diff or not diff.strip():
            return None

        if security:
            rubric = (
                "You are a security reviewer. Audit ONLY the diff below for "
                "security vulnerabilities. Cover these categories: injection "
                "(SQL/command/template), authentication & authorization flaws, "
                "secrets or credentials committed, unsafe deserialization, path "
                "traversal, SSRF, insecure crypto, and unvalidated input. "
                "Do NOT modify any files."
            )
        else:
            rubric = (
                "You are a code reviewer. Review ONLY the diff below for bugs, "
                "logic errors, edge cases, error handling gaps, and "
                "maintainability issues. Do NOT modify any files."
            )

        return (
            f"{rubric}\n\n"
            "For each finding report: severity (high/medium/low), the "
            "file:line it applies to, and a short rationale. If you find no "
            "issues, say so explicitly.\n\n"
            "```diff\n"
            f"{diff}\n"
            "```"
        )

    def _queue_or_execute(
        self, prompt: str, skip_file_mentions: bool = False, read_only: bool = False
    ):
        """Queue prompt if processing, otherwise execute immediately.

        ``skip_file_mentions`` and ``read_only`` propagate to background
        execution so generated prompts (e.g. review diffs) skip ``@file``
        expansion and run against the write-restricted review agent, even when
        drained from the queue on a later turn.
        """
        if self._processing:
            # Add to queue
            self._prompt_queue.append(prompt)
            if skip_file_mentions:
                self._no_mention_prompts.add(id(prompt))
            if read_only:
                self._read_only_prompts.add(id(prompt))
            self.messages.append(ChatMessage(role="system", content=f"Queued: {prompt[:50]}..."))
            self._update_output()
        else:
            # Execute immediately
            self.messages.append(ChatMessage(role="user", content=prompt))
            self._update_output()
            self._execute_in_background(
                prompt, skip_file_mentions=skip_file_mentions, read_only=read_only
            )
    
    def run(self) -> None:
        """Run the async TUI."""
        import asyncio
        
        self._running = True
        
        # Start runtime (ACP/LSP servers) before TUI
        try:
            # Use the shared async bridge instead of a throwaway loop so
            # per-loop connection pools are preserved for later turns. This is a
            # wrapper-only optimisation; the surrounding except degrades to
            # running without the shared bridge when it is unavailable.
            from praisonai_code._wrapper_bridge import import_wrapper_module
            run_sync_or_offload = import_wrapper_module(
                "praisonai._async_bridge"
            ).run_sync_or_offload
            run_sync_or_offload(
                self._start_runtime(),
                thread_name="praisonai-tui-runtime",
            )
            # Runtime status logged to debug file only (not shown in UI)
            # Tools are available silently when runtime is ready
        except Exception as e:
            # Continue without runtime
            self.messages.append(ChatMessage(
                role="system",
                content=f"Runtime unavailable: {e}"
            ))
        
        try:
            self._run_with_prompt_toolkit()
        except ImportError:
            self._run_simple()
    
    def _run_simple(self) -> None:
        """Simple fallback mode without prompt_toolkit."""
        print(self._format_output())
        
        while self._running:
            try:
                if self.config.show_status_bar:
                    status = f" ? for help | {self.config.model} | Session: {self.session_id} "
                    print(f"\033[90m{status}\033[0m")
                
                user_input = input("› ").strip()
                
                if not user_input:
                    continue
                
                if user_input.startswith("/"):
                    before = len(self.messages)
                    self._handle_command(user_input)
                    # Commands like /continue clear and repopulate the message
                    # list with restored user/assistant turns. Render every
                    # newly-appended message (not just system lines) so the
                    # replayed conversation is visible in fallback mode too.
                    new_msgs = self.messages[before:] if len(self.messages) >= before else list(self.messages)
                    for msg in new_msgs:
                        if msg.role == "user":
                            print(f"› {msg.content}")
                        elif msg.role == "assistant":
                            print(f"● {msg.content}")
                        else:
                            print(f"  {msg.content}")
                    # Drop rendered system lines; keep user/assistant turns as
                    # conversational context for subsequent prompts.
                    self.messages = [m for m in self.messages if m.role != "system"]
                    continue
                
                self.messages.append(ChatMessage(role="user", content=user_input))
                print("  ⏳ Praison AI is thinking... (Ctrl-C to interrupt)")
                response = self._execute_prompt_interruptible(user_input)
                
                if response:
                    self.messages.append(ChatMessage(role="assistant", content=response))
                    print(f"\n● {response}\n")
                
            except KeyboardInterrupt:
                print("\n  Use /exit to quit")
            except EOFError:
                self._running = False
        
        print("\n  Goodbye from Praison AI!")
    
    def _run_with_prompt_toolkit(self) -> None:
        """Run with prompt_toolkit for non-blocking split-pane layout."""
        from prompt_toolkit import Application
        from prompt_toolkit.buffer import Buffer
        from prompt_toolkit.document import Document
        from prompt_toolkit.layout.containers import HSplit, VSplit, Window, Float, FloatContainer
        from prompt_toolkit.layout.controls import BufferControl, FormattedTextControl
        from prompt_toolkit.layout.layout import Layout
        from prompt_toolkit.layout.margins import ScrollbarMargin
        from prompt_toolkit.layout.menus import CompletionsMenu
        from prompt_toolkit.key_binding import KeyBindings
        from prompt_toolkit.styles import Style
        from prompt_toolkit.history import FileHistory
        from prompt_toolkit.completion import Completer, Completion
        
        # Create completer for commands and files. Start from the built-ins
        # (single source of truth so registration and autocomplete never drift,
        # e.g. code-review/security-review) and extend with discovered registry
        # commands — custom ``.praisonai/commands/*.md`` and installed skills —
        # so typing ``/`` offers them too. Degrades to built-ins on any failure.
        commands = list(self._BUILTIN_COMMANDS.keys())
        registry = self._get_registry()
        if registry is not None:
            try:
                for c in registry.list_commands():
                    if c.name not in commands:
                        commands.append(c.name)
            except Exception as exc:  # pragma: no cover - defensive
                logger.debug("Skipping registry completions: %s", exc)
        workspace_files = self._workspace_files
        
        class PraisonCompleter(Completer):
            def get_completions(self, document, complete_event):
                text = document.text_before_cursor
                
                # Get the current word being typed
                # Handle case where text might be empty or have no words
                if not text:
                    return
                
                # Find the current word (last word or partial word)
                words = text.split()
                if not words:
                    current_word = text
                elif text.endswith(' '):
                    current_word = ""
                else:
                    current_word = words[-1]
                
                # Show all slash commands when "/" is typed
                if current_word == "/":
                    for cmd in commands:
                        yield Completion(f"/{cmd}", start_position=-1, display=f"/{cmd}", display_meta="command")
                # Filter slash commands
                elif current_word.startswith("/"):
                    cmd_part = current_word[1:].lower()
                    for cmd in commands:
                        if cmd.lower().startswith(cmd_part):
                            yield Completion(f"/{cmd}", start_position=-len(current_word), display=f"/{cmd}", display_meta="command")
                
                # Show all files when "@" is typed
                elif current_word == "@":
                    for f in workspace_files[:30]:
                        yield Completion(f"@{f}", start_position=-1, display=f"@{f}", display_meta="file")
                # Filter @ file mentions
                elif current_word.startswith("@"):
                    file_part = current_word[1:].lower()
                    for f in workspace_files[:50]:
                        if file_part in f.lower():
                            yield Completion(f"@{f}", start_position=-len(current_word), display=f"@{f}", display_meta="file")
        
        # Setup history
        history_file = self.config.history_file or str(Path.home() / ".praison" / "history")
        Path(history_file).parent.mkdir(parents=True, exist_ok=True)
        
        # Output buffer (read-only, scrollable)
        initial_output = self._format_output()
        self._output_buffer = Buffer(
            document=Document(initial_output, cursor_position=len(initial_output)),
            read_only=True,
            name="output"
        )
        
        # Scroll offset for output
        self._scroll_offset = 0
        
        # Input buffer with completer and auto-complete on typing
        input_buffer = Buffer(
            multiline=False,
            history=FileHistory(history_file),
            name="input",
            completer=PraisonCompleter(),
            complete_while_typing=True,  # Show completions as you type
        )
        
        # Key bindings
        kb = KeyBindings()
        
        @kb.add("enter")
        def handle_enter(event):
            user_input = input_buffer.text.strip()
            if not user_input:
                return
            
            input_buffer.reset()
            
            # Handle commands (always process immediately)
            if user_input.startswith("/"):
                self._handle_command(user_input)
                self._update_output()
                return
            
            # NOTE: @file mentions are expanded once, canonically, inside
            # _execute_in_background (which every queued/immediate prompt flows
            # through). Do NOT expand here as well: _process_file_mentions is not
            # idempotent, so a second pass would re-interpret @tokens embedded in
            # already-attached file contents and append unrequested files.
            self._queue_or_execute(user_input)
        
        @kb.add("c-c")
        def handle_ctrl_c(event):
            # If a turn is in flight, request cooperative cancellation so the
            # core chat loop stops at its next step boundary while keeping the
            # warm agent and session intact. Otherwise just clear the input.
            if self._processing and self._interrupt_controller is not None:
                self._interrupt_controller.request("user")
                self._status_text = "⏹ Interrupting… (finishing current step)"
                self._update_output()
            else:
                input_buffer.reset()
        
        @kb.add("c-d")
        def handle_ctrl_d(event):
            if not input_buffer.text:
                self._running = False
                event.app.exit()
        
        @kb.add("c-q")
        def handle_ctrl_q(event):
            self._running = False
            event.app.exit()
        
        # Scroll bindings for output
        @kb.add("pageup")
        def handle_pageup(event):
            self._output_buffer.cursor_up(count=10)
        
        @kb.add("pagedown")
        def handle_pagedown(event):
            self._output_buffer.cursor_down(count=10)
        
        @kb.add("c-up")
        def handle_ctrl_up(event):
            self._output_buffer.cursor_up(count=3)
        
        @kb.add("c-down")
        def handle_ctrl_down(event):
            self._output_buffer.cursor_down(count=3)
        
        @kb.add("home")
        def handle_home(event):
            self._output_buffer.cursor_position = 0
        
        @kb.add("end")
        def handle_end(event):
            self._output_buffer.cursor_position = len(self._output_buffer.text)
        
        # Style
        style = Style.from_dict({
            "output-area": "bg:#0d0d0d",
            "input-area": "bg:#1a1a1a",
            "status-bar": "bg:#333333 #888888",
            "prompt": "#00aaff bold",
            "scrollbar.background": "bg:#333333",
            "scrollbar.button": "bg:#666666",
        })
        
        # Status bar
        def get_status_bar():
            if self._processing:
                return f" {self._status_text} "
            left = "? for help | PageUp/Down to scroll"
            center = self.config.model
            right = f"Session: {self.session_id}"
            plan = "[PLAN] " if self.config.plan_mode else ""
            return f" {plan}{left}  |  {center}  |  {right} "
        
        # Layout: Output (top, scrollable) + Status bar + Input (bottom, fixed)
        # Use FloatContainer to show completion menu as floating overlay
        main_layout = HSplit([
            # Output area (scrollable with scrollbar)
            Window(
                content=BufferControl(
                    buffer=self._output_buffer,
                    focusable=False,
                ),
                wrap_lines=True,
                style="class:output-area",
                right_margins=[ScrollbarMargin(display_arrows=True)],
            ),
            # Status bar (1 line)
            Window(
                content=FormattedTextControl(get_status_bar),
                height=1,
                style="class:status-bar",
            ),
            # Input area (fixed at bottom)
            HSplit([
                Window(height=1),  # Spacer
                VSplit([
                    Window(
                        content=FormattedTextControl([("class:prompt", "› ")]),
                        width=2,
                    ),
                    Window(
                        content=BufferControl(buffer=input_buffer),
                        wrap_lines=True,
                    ),
                ]),
                Window(height=1),  # Spacer
            ], height=3, style="class:input-area"),
        ])
        
        # Wrap in FloatContainer to show completions menu
        layout = Layout(
            FloatContainer(
                content=main_layout,
                floats=[
                    Float(
                        xcursor=True,
                        ycursor=True,
                        content=CompletionsMenu(max_height=10, scroll_offset=1),
                    ),
                ],
            )
        )
        
        # Create application
        self._app = Application(
            layout=layout,
            key_bindings=kb,
            style=style,
            full_screen=True,
            mouse_support=True,
            refresh_interval=0.1,  # Refresh every 100ms for spinner
        )
        
        # Run
        self._app.run()
        
        print("\n  Goodbye from Praison AI!")
    
    def run_single(self, prompt: str) -> Optional[str]:
        """Run a single prompt (non-interactive)."""
        return self._execute_prompt(prompt)

    @property
    def execution_failed(self) -> bool:
        """True if the last prompt execution failed (e.g. auth error).

        Lets the CLI propagate a non-zero exit code on failure (issue #2562).
        """
        return self._last_error is not None


def start_async_tui(
    model: str = "gpt-4o-mini",
    show_logo: bool = True,
    **kwargs
) -> None:
    """Start the async TUI application."""
    config = AsyncTUIConfig(
        model=model,
        show_logo=show_logo,
    )
    
    tui = AsyncTUI(config=config)
    tui.run()
