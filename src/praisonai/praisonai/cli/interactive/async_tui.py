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
        self._processing = False
        self._status_text = ""
        self._last_error: Optional[Exception] = None
        self._app = None
        self._output_buffer = None
        self._prompt_queue: List[str] = []  # Queue for pending prompts
        self._conversation_history: List[dict] = []  # Full conversation history
        self._total_tokens = 0
        self._total_cost = 0.0
        self._workspace_files: List[str] = []  # Files in workspace for @ completion
        self._runtime = None  # InteractiveRuntime for ACP/LSP
        self._runtime_started = False
        self._registry = None  # Unified command registry (lazy)
        
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
    
    def _get_agent(self):
        """Lazy-load the agent with tools."""
        if self._agent is None:
            logger.debug("Creating new agent...")
            try:
                from praisonaiagents import Agent
                
                # Load interactive tools (read_file, write_file, execute_command, etc.)
                tools = self._load_tools()
                logger.debug(f"Tools for agent: {len(tools) if tools else 0}")
                
                # Auto-inject project instruction files unless disabled
                instructions = "You are Praison AI, a helpful assistant. Be concise and helpful. You have access to tools for file operations, code execution, and web search."
                max_chars = 32000  # Default cap
                
                # Check config for rules settings with proper precedence
                try:
                    from praisonai.cli.configuration.loader import load_config
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
                
                logger.debug(f"Agent config: model={self.config.model}, tools={len(tools) if tools else 0}")
                self._agent = Agent(**agent_config)
                logger.debug("Agent created successfully")
            except ImportError as e:
                logger.error(f"Failed to import praisonaiagents: {e}")
                raise RuntimeError(f"Failed to import praisonaiagents: {e}")
        
        return self._agent
    
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
                lsp=True,
                acp=True,
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
        
        # Try to load all interactive tools (basic + ACP + LSP)
        try:
            from praisonai_code.cli.features.interactive_tools import get_interactive_tools
            tools = get_interactive_tools(
                groups=["basic", "acp", "lsp"],  # All tool groups
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
        "status": "Show ACP/LSP runtime status",
        "auto": "Toggle autonomy mode (auto-delegate complex tasks)",
        "debug": "Toggle debug logging",
        "plan": "Create a step-by-step plan for a task",
        "handoff": "Delegate to specialized agent (code/research/review/docs)",
        "compact": "Toggle compact output mode",
        "multiline": "Toggle multiline input mode",
        "files": "List workspace files for @ mentions",
        "queue": "Show pending prompts in queue",
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
                    self._BUILTIN_COMMANDS, include_custom=True
                )
            except Exception as exc:  # pragma: no cover - defensive
                logger.debug("Command registry unavailable: %s", exc)
                self._registry = _REGISTRY_FAILED
        if self._registry is _REGISTRY_FAILED:
            return None
        return self._registry

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
  /status          Show ACP/LSP runtime status
  /auto            Toggle autonomy mode (auto-delegate complex tasks)
  /debug           Toggle debug logging to ~/.praisonai/async_tui_debug.log
  /plan <task>     Create a step-by-step plan for a task
  /handoff <type> <task>  Delegate to specialized agent (code/research/review/docs)
  /compact         Toggle compact output mode
  /multiline       Toggle multiline input mode
  /files           List workspace files for @ mentions
  /queue           Show pending prompts in queue

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
        
        elif cmd == "cost":
            cost_info = f"Total tokens: {self._total_tokens}\nEstimated cost: ${self._total_cost:.4f}"
            self.messages.append(ChatMessage(role="system", content=cost_info))
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
                from praisonai.cli.session import get_session_store
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
                from praisonai.cli.session import get_session_store
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
                            # Load history
                            history = session.get_chat_history()
                            self._conversation_history = history
                            self.messages.append(ChatMessage(
                                role="system", 
                                content=f"Continued session: {self.session_id} ({len(history)} messages)"
                            ))
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
            # Planning mode - create a plan for a complex task
            if not args:
                self.messages.append(ChatMessage(
                    role="system", 
                    content="Usage: /plan <task description>\nCreates a step-by-step plan before execution."
                ))
            else:
                # Execute with planning enabled
                self.messages.append(ChatMessage(role="system", content=f"📋 Creating plan for: {args}"))
                self._update_output()
                
                # Use planning agent to create plan
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
    
    def _execute_prompt(self, prompt: str) -> Optional[str]:
        """Execute a prompt and return the response (suppresses agent output)."""
        import sys
        import io
        import asyncio
        
        logger.debug(f"Executing prompt: {prompt[:100]}...")
        
        self._last_error = None
        try:
            agent = self._get_agent()
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
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)
                        response = loop.run_until_complete(agent.astart(prompt))
                        loop.close()
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
    
    def _execute_in_background(self, prompt: str):
        """Execute prompt in background thread (non-blocking)."""
        # Track tool calls for visibility
        tool_calls = []
        
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
        
        # Register callback for tool visibility
        _sync_display_callbacks = None
        _register_display_callback = None
        try:
            from praisonaiagents import register_display_callback, sync_display_callbacks
            _sync_display_callbacks = sync_display_callbacks
            _register_display_callback = register_display_callback
            _register_display_callback('tool_call', tool_call_callback)
        except ImportError:
            pass
        
        def run():
            self._processing = True
            self._status_text = "Praison AI is thinking..."
            self._update_output()
            
            # Process @file mentions
            processed_prompt = self._process_file_mentions(prompt)
            
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
                    result[0] = self._execute_prompt(processed_prompt)
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
            
            # Cleanup callback
            if _sync_display_callbacks is not None and 'tool_call' in _sync_display_callbacks:
                del _sync_display_callbacks['tool_call']
            
            # Done processing current prompt
            self._processing = False
            self._status_text = ""
            
            # Show tool calls summary if any were made
            if tool_calls:
                tools_used = ", ".join(tool_calls)
                self.messages.append(ChatMessage(role="system", content=f"Tools used: {tools_used}"))
            
            if error[0]:
                self.messages.append(ChatMessage(role="assistant", content=f"Error: {error[0]}"))
                self._conversation_history.append({"role": "assistant", "content": f"Error: {error[0]}"})
            elif result[0]:
                self.messages.append(ChatMessage(role="assistant", content=result[0]))
                self._conversation_history.append({"role": "assistant", "content": result[0]})
            
            self._update_output()
            
            # Process next item in queue if any
            if self._prompt_queue:
                next_prompt = self._prompt_queue.pop(0)
                self.messages.append(ChatMessage(role="user", content=next_prompt))
                self._update_output()
                self._execute_in_background(next_prompt)
        
        # Run in background thread
        thread = threading.Thread(target=run, daemon=True)
        thread.start()
    
    def _queue_or_execute(self, prompt: str):
        """Queue prompt if processing, otherwise execute immediately."""
        if self._processing:
            # Add to queue
            self._prompt_queue.append(prompt)
            self.messages.append(ChatMessage(role="system", content=f"Queued: {prompt[:50]}..."))
            self._update_output()
        else:
            # Execute immediately
            self.messages.append(ChatMessage(role="user", content=prompt))
            self._update_output()
            self._execute_in_background(prompt)
    
    def run(self) -> None:
        """Run the async TUI."""
        import asyncio
        
        self._running = True
        
        # Start runtime (ACP/LSP servers) before TUI
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(self._start_runtime())
            loop.close()
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
                    self._handle_command(user_input)
                    for msg in self.messages:
                        if msg.role == "system":
                            print(f"  {msg.content}")
                    self.messages = [m for m in self.messages if m.role != "system"]
                    continue
                
                self.messages.append(ChatMessage(role="user", content=user_input))
                print("  ⏳ Praison AI is thinking...")
                response = self._execute_prompt(user_input)
                
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
        
        # Create completer for commands and files
        commands = ["help", "exit", "quit", "clear", "new", "model", "session", "sessions",
                    "continue", "history", "export", "import", "cost", "status", "auto",
                    "debug", "plan", "handoff", "compact", "multiline", "files", "queue"]
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
            
            # Queue or execute prompt
            self._queue_or_execute(user_input)
        
        @kb.add("c-c")
        def handle_ctrl_c(event):
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
            return f" {left}  |  {center}  |  {right} "
        
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
