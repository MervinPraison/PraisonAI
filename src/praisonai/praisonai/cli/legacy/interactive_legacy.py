"""Interactive REPL/TUI legacy path (C8.4)."""

from __future__ import annotations

import argparse
import json
import logging
import os
import shutil
import subprocess
import sys
import time
import yaml
from dotenv import load_dotenv
from rich import print
from praisonai.cli.legacy.subcommand_handlers import _load_cli_project_context

def _start_interactive_mode(self, args):
    """
    Start interactive TUI mode with streaming responses and tool support.
    
    UX inspired by Gemini CLI, Codex CLI, and Claude Code:
    - Streaming text output (no boxes)
    - Tool status indicators
    - Built-in tools (file ops, shell, web search)
    - Autocomplete for slash commands and @file mentions
    - /compact for context compression
    - /model for model switching
    - /stats for token/cost tracking
    - /undo for reverting changes
    """
    try:
        from rich.console import Console
        import os
        
        console = Console()
        
        # Persist the caller's args (e.g. from `praisonai code`) so the
        # agent-creation path can read the named-agent profile, approval
        # config, and reasoning effort via self.args. Without this the
        # --agent/--thinking flags resolved in code.py are silently dropped.
        if args is not None:
            self.args = args
        
        # Set interactive mode flag
        self._interactive_mode = True
        
        # Load interactive tools
        tools_list = _load_interactive_tools(self)
        
        # Import message queue components
        from ..features.message_queue import (
            MessageQueue, StateManager, QueueDisplay, ProcessingState,
            LiveStatusDisplay
        )
        import threading
        import queue as queue_module
        
        # Create message queue and state manager
        message_queue = MessageQueue()
        state_manager = StateManager()
        queue_display = QueueDisplay(message_queue, state_manager)
        live_status = LiveStatusDisplay()
        processing_lock = threading.Lock()
        
        # Create execution queue for worker thread (TRUE ASYNC)
        execution_queue = queue_module.Queue()
        approval_request_queue = queue_module.Queue()
        approval_response_queue = queue_module.Queue()
        
        # Worker state for cross-thread communication
        # Enhanced with task-bound context for proper Q/A mapping
        worker_state = {
            'running': True,
            'current_task': None,  # Full task context object (FIFO head)
            'approval_pending': False,
            'waiting_for_approval_input': False,
            'completed_tasks': [],  # Queue of completed tasks to display (FIFO order)
            'error_tasks': [],  # Queue of error tasks to display
            'tool_activity': None,  # Current tool being used
            'last_status_line': None,  # For transient status updates
        }
        
        # Task counter for unique IDs (FIFO position tracking)
        task_counter = {'value': 0}
        
        # Check for verbose mode
        verbose_mode = getattr(args, 'verbose', False) if hasattr(args, 'verbose') else False
        
        # Initialize persistent session
        from .session import get_session_store
        session_store = get_session_store()
        
        # Check for --resume flag or get/create session
        resume_session_id = getattr(args, 'resume_session', None)
        if resume_session_id == 'last':
            unified_session = session_store.get_last_session()
            if not unified_session:
                unified_session = session_store.get_or_create()
        elif resume_session_id:
            unified_session = session_store.get_or_create(resume_session_id)
        else:
            unified_session = session_store.get_or_create()
        
        # Set model from args or session
        current_model = getattr(args, 'llm', None) or unified_session.current_model or os.environ.get('OPENAI_MODEL_NAME', 'gpt-4o-mini')
        unified_session.current_model = current_model
        
        # Session state (now backed by persistent UnifiedSession)
        session_state = {
            'show_profiling': False,
            'current_model': current_model,
            'conversation_history': unified_session.get_chat_history(),
            'total_input_tokens': unified_session.total_input_tokens,
            'total_output_tokens': unified_session.total_output_tokens,
            'total_cost': unified_session.total_cost,
            'request_count': unified_session.request_count,
            'undo_stack': [],  # Stack of (prompt, response) for undo
            'message_queue': message_queue,
            'state_manager': state_manager,
            'queue_display': queue_display,
            'live_status': live_status,
            'processing_lock': processing_lock,
            'execution_queue': execution_queue,  # Queue for worker thread
            'approval_request_queue': approval_request_queue,
            'approval_response_queue': approval_response_queue,
            'worker_state': worker_state,
            'unified_session': unified_session,  # Reference to persistent session
            'session_store': session_store,  # Reference to store for saving
        }
        
        # Initialize context manager with CLI flags
        context_config = {
            'auto_compact': getattr(args, 'context_auto_compact', True),  # Default True in interactive
            'strategy': getattr(args, 'context_strategy', 'smart'),
            'threshold': getattr(args, 'context_threshold', 0.8),
            'monitor_enabled': getattr(args, 'context_monitor', False),
            'monitor_path': getattr(args, 'context_monitor_path', './context.txt'),
            'monitor_format': getattr(args, 'context_monitor_format', 'human'),
            'monitor_frequency': getattr(args, 'context_monitor_frequency', 'turn'),
            'redact_sensitive': getattr(args, 'context_redact', True),
            'output_reserve': getattr(args, 'context_output_reserve', 8000),
        }
        session_state['context_config'] = context_config

        # Wire turn-aware workspace checkpointing into the session lifecycle.
        # Reuses the core CheckpointService via CheckpointsHandler; default
        # safe (disabled unless checkpoints.auto in config or
        # PRAISONAI_CHECKPOINTS=on), so there is zero overhead when off.
        try:
            from ..features.session_checkpoints import (
                SessionCheckpointManager,
            )
            checkpoint_config = None
            try:
                from ..configuration.resolver import resolve_config
                checkpoint_config = resolve_config().extra
            except Exception:
                checkpoint_config = None
            session_checkpoints = SessionCheckpointManager.from_config(
                workspace_dir=os.environ.get("PRAISONAI_WORKSPACE") or os.getcwd(),
                config=checkpoint_config,
                verbose=verbose_mode,
            )
            if session_checkpoints.enabled:
                # Baseline checkpoint at session start.
                session_checkpoints.checkpoint_turn("session start")
        except Exception:
            session_checkpoints = None
        session_state['session_checkpoints'] = session_checkpoints

        # Start the execution worker thread (TRUE ASYNC - runs in background)
        worker_thread = _start_execution_worker(self, tools_list, console, session_state)
        
        # Try to use prompt_toolkit for autocomplete
        prompt_session = None
        try:
            from prompt_toolkit import PromptSession
            from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
            from prompt_toolkit.history import InMemoryHistory
            from ..features.at_mentions import CombinedCompleter
            
            # Create combined completer for / commands and @ mentions
            commands = ['help', 'exit', 'quit', 'clear', 'tools', 'profile', 'model', 'stats', 'compact', 'undo', 'revert', 'queue', 'q']
            combined_completer = CombinedCompleter(
                commands=commands,
                root_dir=os.getcwd()
            )
            
            prompt_session = PromptSession(
                message="❯ ",
                completer=combined_completer,
                auto_suggest=AutoSuggestFromHistory(),
                history=InMemoryHistory(),
                complete_while_typing=True
            )
        except ImportError:
            pass  # Fall back to simple input
        
        # Print welcome message
        console.print("\n[bold cyan]PraisonAI Interactive Mode[/bold cyan]")
        console.print("[dim]Type your prompt, use /help for commands, /exit to quit[/dim]")
        console.print(f"[dim]Model: {session_state['current_model']} | Tools: {len(tools_list)} | Session: {unified_session.session_id}[/dim]")
        if unified_session.message_count > 0:
            console.print(f"[dim]Resumed session with {unified_session.message_count} messages[/dim]")
        console.print("[dim]Use @file.txt to include file content | Queue messages while processing[/dim]\n")
        
        # Start display thread for status updates (non-blocking)
        import time
        from rich.panel import Panel
        
        display_running = {'value': True}
        
        def display_loop():
            """Background thread for status display - NEVER blocks input.
            
            FIFO-aligned display:
            - Default mode: Minimal, calm output. Just show response.
            - Verbose mode: Full task lifecycle with IDs, times, word counts.
            """
            while display_running['value']:
                try:
                    # Check for completed tasks to display (FIFO order guaranteed)
                    if worker_state['completed_tasks']:
                        task = worker_state['completed_tasks'].pop(0)
                        response = task.get('response', '')
                        
                        # Clear any transient status line
                        if worker_state.get('last_status_line'):
                            console.print("\r" + " " * 80 + "\r", end="")
                            worker_state['last_status_line'] = None
                        
                        console.print()  # New line before response
                        
                        if verbose_mode:
                            # VERBOSE: Full task lifecycle with metadata
                            question = task.get('question', '')
                            task_id = task.get('task_id', 0)
                            elapsed = task.get('elapsed', 0)
                            word_count = len(response.split()) if response else 0
                            q_display = question[:80] + "..." if len(question) > 80 else question
                            
                            console.print(f"[bold cyan]─── Task #{task_id} completed ({elapsed:.1f}s, {word_count} words) ───[/bold cyan]")
                            console.print(f"[bold green]Q:[/bold green] {q_display}")
                            console.print(f"[bold blue]A:[/bold blue] ", end="")
                        
                        # Stream response (both modes)
                        if response:
                            words = response.split()
                            for i, word in enumerate(words):
                                console.print(word + " ", end="")
                                if i % 20 == 19:
                                    time.sleep(0.003)
                        console.print()
                        
                        if verbose_mode:
                            task_id = task.get('task_id', 0)
                            console.print(f"[dim]─── End Task #{task_id} ───[/dim]")
                        console.print()
                    
                    # Check for error tasks to display
                    if worker_state['error_tasks']:
                        task = worker_state['error_tasks'].pop(0)
                        error = task.get('error', '')
                        
                        # Clear transient status
                        if worker_state.get('last_status_line'):
                            console.print("\r" + " " * 80 + "\r", end="")
                            worker_state['last_status_line'] = None
                        
                        console.print()
                        if verbose_mode:
                            question = task.get('question', '')
                            task_id = task.get('task_id', 0)
                            q_display = question[:80] + "..." if len(question) > 80 else question
                            console.print(f"[bold red]─── Task #{task_id} failed ───[/bold red]")
                            console.print(f"[bold green]Q:[/bold green] {q_display}")
                        console.print(f"[red]Error: {error}[/red]")
                        console.print()
                    
                    # Check for approval requests
                    try:
                        approval_info = approval_request_queue.get_nowait()
                        
                        function_name = approval_info['function_name']
                        arguments = approval_info['arguments']
                        risk_level = approval_info['risk_level']
                        
                        risk_colors = {"critical": "bold red", "high": "red", "medium": "yellow", "low": "blue"}
                        risk_color = risk_colors.get(risk_level, "white")
                        
                        # Clear transient status
                        if worker_state.get('last_status_line'):
                            console.print("\r" + " " * 80 + "\r", end="")
                            worker_state['last_status_line'] = None
                        
                        console.print()
                        
                        # Show approval panel (both modes)
                        tool_info = f"[bold]Function:[/] {function_name}\n"
                        tool_info += f"[bold]Risk Level:[/] [{risk_color}]{risk_level.upper()}[/{risk_color}]\n"
                        tool_info += "[bold]Arguments:[/]\n"
                        for key, value in arguments.items():
                            str_value = str(value)[:100] + "..." if len(str(value)) > 100 else str(value)
                            tool_info += f"  {key}: {str_value}\n"
                        
                        console.print(Panel(tool_info.strip(), title="🔒 Tool Approval Required", border_style=risk_color))
                        console.print(f"[{risk_color}]Type 'y' to approve, 'n' to reject:[/{risk_color}] ", end="")
                        
                        worker_state['waiting_for_approval_input'] = True
                        
                    except queue_module.Empty:
                        pass
                    
                    # Show FIFO head status (transient, both modes)
                    current_task = worker_state.get('current_task')
                    if current_task and not worker_state.get('waiting_for_approval_input'):
                        queue_size = execution_queue.qsize()
                        prompt_preview = current_task.get('question', '')[:50]
                        if len(current_task.get('question', '')) > 50:
                            prompt_preview += "..."
                        
                        # Build status line
                        tool_activity = worker_state.get('tool_activity')
                        if tool_activity and tool_activity.get('status') == 'started':
                            tool_name = tool_activity.get('name', '')
                            status_line = f"⚙️  {tool_name}"
                        else:
                            status_line = f"⏳ Processing: {prompt_preview}"
                        
                        if queue_size > 0:
                            status_line += f" | 📋 {queue_size} waiting"
                        
                        # Only update if changed (avoid flicker)
                        if status_line != worker_state.get('last_status_line'):
                            console.print(f"\r[dim cyan]{status_line}[/dim cyan]" + " " * 20, end="\r")
                            worker_state['last_status_line'] = status_line
                    elif not current_task and worker_state.get('last_status_line'):
                        # Clear status when idle
                        console.print("\r" + " " * 80 + "\r", end="")
                        worker_state['last_status_line'] = None
                    
                    time.sleep(0.1)
                except Exception:
                    pass
        
        # Start display thread
        display_thread = threading.Thread(target=display_loop, daemon=True, name="DisplayLoop")
        display_thread.start()
        
        running = True
        while running:
            try:
                # Get user input (with autocomplete if available)
                # This is NON-BLOCKING relative to LLM execution
                # Status is shown by the display thread, not here
                if prompt_session:
                    user_input = prompt_session.prompt().strip()
                else:
                    user_input = input("❯ ").strip()
                
                if not user_input:
                    continue
                
                # Check if this is an approval response
                if worker_state.get('waiting_for_approval_input'):
                    try:
                        from praisonaiagents.approval import ApprovalDecision
                        if user_input.lower() in ['y', 'yes', 'approve']:
                            console.print("[green]✅ Approved[/green]")
                            approval_response_queue.put(ApprovalDecision(approved=True, reason="User approved"))
                        else:
                            console.print("[red]❌ Denied[/red]")
                            approval_response_queue.put(ApprovalDecision(approved=False, reason="User denied"))
                        worker_state['waiting_for_approval_input'] = False
                        continue
                    except ImportError:
                        pass
                
                # Handle slash commands
                if user_input.startswith("/"):
                    cmd_parts = user_input[1:].split(maxsplit=1)
                    cmd = cmd_parts[0].lower() if cmd_parts else ""
                    cmd_args = cmd_parts[1] if len(cmd_parts) > 1 else ""
                    
                    if cmd in ["exit", "quit", "q"]:
                        console.print("[dim]Goodbye![/dim]")
                        running = False
                        worker_state['running'] = False
                        display_running['value'] = False
                        continue
                    elif cmd == "help":
                        _print_interactive_help(self, console)
                        continue
                    elif cmd == "clear":
                        console.clear()
                        continue
                    elif cmd == "tools":
                        console.print(f"[cyan]Available tools: {len(tools_list)}[/cyan]")
                        for tool in tools_list:
                            name = getattr(tool, '__name__', str(tool))
                            console.print(f"  • {name}")
                        continue
                    elif cmd == "profile":
                        session_state['show_profiling'] = not session_state['show_profiling']
                        status = "enabled" if session_state['show_profiling'] else "disabled"
                        console.print(f"[cyan]Profiling {status}[/cyan]")
                        continue
                    elif cmd == "model":
                        _handle_model_command(self, console, cmd_args, session_state)
                        continue
                    elif cmd == "stats":
                        _handle_stats_command(self, console, session_state)
                        continue
                    elif cmd == "compact":
                        _handle_compact_command(self, console, session_state)
                        continue
                    elif cmd == "context":
                        _handle_context_command(self, console, cmd_args, session_state)
                        continue
                    elif cmd == "undo":
                        _handle_undo_command(self, console, session_state)
                        continue
                    elif cmd == "revert":
                        _handle_revert_command(self, console, cmd_args, session_state)
                        continue
                    elif cmd == "queue":
                        _handle_queue_command(self, console, cmd_args, session_state)
                        continue
                    elif cmd == "session":
                        # Show session info
                        us = session_state.get('unified_session')
                        if us:
                            console.print(f"[cyan]Session ID:[/cyan] {us.session_id}")
                            console.print(f"[cyan]Messages:[/cyan] {us.message_count}")
                            console.print(f"[cyan]Created:[/cyan] {us.created_at}")
                            console.print(f"[cyan]Updated:[/cyan] {us.updated_at}")
                            console.print(f"[cyan]Total tokens:[/cyan] {us.total_input_tokens + us.total_output_tokens}")
                        continue
                    elif cmd == "history":
                        # Show conversation history
                        us = session_state.get('unified_session')
                        if us and us.messages:
                            console.print(f"[cyan]Conversation history ({len(us.messages)} messages):[/cyan]")
                            for i, msg in enumerate(us.messages[-10:]):  # Show last 10
                                role = msg.get('role', 'unknown')
                                content = msg.get('content', '')[:100]
                                if len(msg.get('content', '')) > 100:
                                    content += "..."
                                style = "green" if role == "user" else "blue"
                                console.print(f"  [{style}]{role}:[/{style}] {content}")
                        else:
                            console.print("[dim]No conversation history[/dim]")
                        continue
                    elif cmd == "new":
                        # Start a new session
                        store = session_state.get('session_store')
                        if store:
                            new_session = store.get_or_create()
                            session_state['unified_session'] = new_session
                            session_state['conversation_history'] = []
                            session_state['total_input_tokens'] = 0
                            session_state['total_output_tokens'] = 0
                            session_state['request_count'] = 0
                            console.print(f"[cyan]Started new session: {new_session.session_id}[/cyan]")
                        continue
                    elif cmd == "status":
                        # Show current processing status
                        current_task = worker_state.get('current_task')
                        current = current_task.get('question') if current_task else None
                        queue_size = execution_queue.qsize()
                        if current:
                            console.print(f"[cyan]Processing:[/cyan] {current}")
                        if queue_size > 0:
                            console.print(f"[cyan]Queued:[/cyan] {queue_size} messages")
                        if not current and queue_size == 0:
                            console.print("[dim]Idle - no messages processing[/dim]")
                        continue
                    else:
                        console.print(f"[yellow]Unknown command: /{cmd}. Type /help for available commands.[/yellow]")
                        continue
                
                # Process @file mentions before sending to LLM
                processed_input = _process_at_mentions(self, user_input, console)
                
                # Auto-checkpoint the workspace before a turn that may
                # mutate files, so /undo and /revert can roll it back.
                # Best-effort: never blocks or breaks the turn.
                _ckpt = session_state.get('session_checkpoints')
                if _ckpt is not None and getattr(_ckpt, 'enabled', False):
                    _ckpt.checkpoint_turn(processed_input[:60])

                # Create task with unique ID and full context
                task_counter['value'] += 1
                task_id = task_counter['value']
                
                task = {
                    'task_id': task_id,
                    'prompt': processed_input,
                    'question': processed_input,  # Full question for Q/A mapping
                    'status': 'queued',
                    'queued_at': time.time(),
                }
                
                # Submit to execution queue - THIS IS NON-BLOCKING (FIFO)
                queue_size = execution_queue.qsize()
                execution_queue.put(task)
                
                # Show queue status (minimal by default, verbose shows task IDs)
                if verbose_mode:
                    q_preview = processed_input[:60] + "..." if len(processed_input) > 60 else processed_input
                    if queue_size > 0:
                        console.print(f"[dim cyan]📋 Task #{task_id} queued (FIFO position {queue_size + 1})[/dim cyan]")
                        console.print(f"[dim]   └─ {q_preview}[/dim]")
                    else:
                        console.print(f"[dim cyan]▶ Task #{task_id} started (FIFO head)[/dim cyan]")
                        console.print(f"[dim]   └─ {q_preview}[/dim]")
                else:
                    # DEFAULT: Minimal, calm output
                    if queue_size > 0:
                        console.print(f"[dim]📋 Queued ({queue_size + 1} in queue)[/dim]")
                
            except KeyboardInterrupt:
                console.print("\n[dim]Use /exit to quit[/dim]")
            except EOFError:
                running = False
                
    except ImportError as e:
        print(f"[red]ERROR: Interactive mode requires rich: {e}[/red]")
        print("Install with: pip install rich")
        sys.exit(1)
    except Exception as e:
        print(f"[red]ERROR: Interactive mode failed: {e}[/red]")
        import traceback
        traceback.print_exc()
        sys.exit(1)

def _load_interactive_tools(self):
    """
    Load tools for interactive mode using the canonical provider.
    
    This method uses the centralized interactive_tools module which provides:
    - ACP tools (acp_create_file, acp_edit_file, etc.) for safe file operations
    - LSP tools (lsp_list_symbols, lsp_find_definition, etc.) for code intelligence
    - Basic tools (read_file, write_file, etc.) for standard operations
    
    Tool groups can be disabled via:
    - CLI flags: --no-acp, --no-lsp
    - Env vars: PRAISON_TOOLS_DISABLE=acp,lsp
    """
    # Determine which groups to disable based on CLI args
    disable_groups = []
    if hasattr(self, 'args'):
        if getattr(self.args, 'no_acp', False):
            disable_groups.append('acp')
        if getattr(self.args, 'no_lsp', False):
            disable_groups.append('lsp')
    
    # Get workspace
    workspace = os.getcwd()
    
    try:
        from ..features.interactive_tools import get_interactive_tools, ToolConfig
        
        # Create config
        config = ToolConfig.from_env()
        config.workspace = workspace
        
        # Apply CLI overrides
        if 'acp' in disable_groups:
            config.enable_acp = False
        if 'lsp' in disable_groups:
            config.enable_lsp = False
        
        # Get tools from canonical provider
        tools_list = get_interactive_tools(
            config=config,
            disable=disable_groups if disable_groups else None,
        )
        
        logging.debug(f"Loaded {len(tools_list)} interactive tools (ACP: {config.enable_acp}, LSP: {config.enable_lsp})")
        return tools_list
        
    except ImportError as e:
        logging.debug(f"Interactive tools provider not available: {e}")
        # Fallback to basic tools only
        return _load_basic_tools_fallback(self, )

def _load_basic_tools_fallback(self):
    """Fallback to load basic tools when interactive_tools module unavailable."""
    tools_list = []
    try:
        from praisonaiagents.tools import (
            read_file as tool_read_file,
            write_file as tool_write_file,
            list_files as tool_list_files,
            execute_command,
            internet_search
        )
        tools_list = [tool_read_file, tool_write_file, tool_list_files, execute_command, internet_search]
    except ImportError:
        # Try individual imports
        try:
            from praisonaiagents.tools import read_file as tool_read_file
            tools_list.append(tool_read_file)
        except ImportError:
            pass
        try:
            from praisonaiagents.tools import write_file as tool_write_file
            tools_list.append(tool_write_file)
        except ImportError:
            pass
        try:
            from praisonaiagents.tools import list_files as tool_list_files
            tools_list.append(tool_list_files)
        except ImportError:
            pass
        try:
            from praisonaiagents.tools import execute_command
            tools_list.append(execute_command)
        except ImportError:
            pass
        try:
            from praisonaiagents.tools import internet_search
            tools_list.append(internet_search)
        except ImportError:
            pass
    return tools_list

def _print_interactive_help(self, console):
    """Print help for interactive mode."""
    console.print("\n[bold]Commands:[/bold]")
    console.print("  /help          - Show this help")
    console.print("  /exit          - Exit interactive mode")
    console.print("  /clear         - Clear screen")
    console.print("  /tools         - List available tools")
    console.print("  /profile       - Toggle profiling (show timing breakdown)")
    console.print("  /model [name]  - Show or change current model")
    console.print("  /stats         - Show session statistics (tokens, cost)")
    console.print("  /compact       - Compress conversation history")
    console.print("  /undo          - Undo last response (and workspace files if checkpointing on)")
    console.print("  /revert [n]    - Roll workspace back n turns (needs checkpoints.auto)")
    console.print("  /queue         - Show queued messages")
    console.print("  /queue clear   - Clear message queue")
    console.print("\n[bold]Session Commands:[/bold]")
    console.print("  /session       - Show current session info")
    console.print("  /history       - Show conversation history")
    console.print("  /new           - Start a new session")
    console.print("\n[bold]@ Mentions:[/bold]")
    console.print("  @file.txt      - Include file content in prompt")
    console.print("  @src/          - Include directory listing")
    console.print("\n[bold]Features:[/bold]")
    console.print("  • File operations (read, write, list)")
    console.print("  • Shell command execution")
    console.print("  • Web search")
    console.print("  • Context compression for long sessions")
    console.print("  • Persistent sessions (auto-saved)")
    console.print("  • Queue messages while agent is processing")
    console.print("")

def _process_at_mentions(self, user_input, console):
    """
    Process @file mentions in user input.
    
    Supports:
    - @file.txt - Include file content
    - @path/to/file - Include file content
    - @directory/ - Include directory listing
    
    Inspired by Gemini CLI and Claude Code @file syntax.
    """
    import re
    import os
    
    # Pattern to match @path (but not email addresses)
    # Must be at start or preceded by whitespace
    pattern = r'(?:^|\s)@([^\s@]+)'
    
    matches = re.findall(pattern, user_input)
    if not matches:
        return user_input
    
    processed_input = user_input
    file_contents = []
    
    for path in matches:
        # Clean up the path
        clean_path = path.strip()
        
        # Expand ~ to home directory
        if clean_path.startswith('~'):
            clean_path = os.path.expanduser(clean_path)
        
        # Make absolute if relative
        if not os.path.isabs(clean_path):
            clean_path = os.path.abspath(clean_path)
        
        try:
            if os.path.isfile(clean_path):
                # Read file content
                with open(clean_path, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()
                
                # Truncate if too large (>50KB)
                if len(content) > 50000:
                    content = content[:50000] + "\n... [truncated, file too large]"
                
                file_contents.append(f"\n--- Content of {path} ---\n{content}\n--- End of {path} ---\n")
                console.print(f"[dim]📄 Included: {path} ({len(content)} chars)[/dim]")
                
            elif os.path.isdir(clean_path):
                # List directory contents
                try:
                    entries = os.listdir(clean_path)
                    # Filter out hidden files and common ignore patterns
                    entries = [e for e in entries if not e.startswith('.') and e not in ['node_modules', '__pycache__', 'venv', '.git']]
                    entries.sort()
                    
                    listing = "\n".join(f"  {e}" for e in entries[:50])
                    if len(entries) > 50:
                        listing += f"\n  ... and {len(entries) - 50} more files"
                    
                    file_contents.append(f"\n--- Directory listing of {path} ---\n{listing}\n--- End of {path} ---\n")
                    console.print(f"[dim]📁 Listed: {path} ({len(entries)} items)[/dim]")
                except PermissionError:
                    console.print(f"[yellow]⚠ Permission denied: {path}[/yellow]")
            else:
                console.print(f"[yellow]⚠ Not found: {path}[/yellow]")
                
        except Exception as e:
            console.print(f"[yellow]⚠ Error reading {path}: {e}[/yellow]")
    
    # Remove @mentions from the original input and append file contents
    for path in matches:
        processed_input = processed_input.replace(f"@{path}", "")
    
    processed_input = processed_input.strip()
    if file_contents:
        processed_input = processed_input + "\n" + "\n".join(file_contents)
    
    return processed_input

def _handle_model_command(self, console, args, session_state):
    """Handle /model command - show or change current model."""
    if not args:
        # Show current model
        console.print(f"[cyan]Current model: {session_state['current_model']}[/cyan]")
        console.print("\n[dim]Available models (examples):[/dim]")
        console.print("  • gpt-4o, gpt-4o-mini")
        console.print("  • claude-3-5-sonnet, claude-3-haiku")
        console.print("  • gemini-2.0-flash, gemini-1.5-pro")
        console.print("\n[dim]Usage: /model <model-name>[/dim]")
    else:
        # Change model
        new_model = args.strip()
        old_model = session_state['current_model']
        session_state['current_model'] = new_model
        console.print(f"[green]✓ Model changed: {old_model} → {new_model}[/green]")

def _handle_stats_command(self, console, session_state):
    """Handle /stats command - show session statistics."""
    from ..features.cost_tracker import get_pricing
    
    console.print("\n[bold cyan]Session Statistics[/bold cyan]")
    console.print(f"  Model:          {session_state['current_model']}")
    console.print(f"  Requests:       {session_state['request_count']}")
    console.print(f"  Input tokens:   {session_state['total_input_tokens']:,}")
    console.print(f"  Output tokens:  {session_state['total_output_tokens']:,}")
    console.print(f"  Total tokens:   {session_state['total_input_tokens'] + session_state['total_output_tokens']:,}")
    
    # Calculate estimated cost
    try:
        pricing = get_pricing(session_state['current_model'])
        cost = pricing.calculate_cost(
            session_state['total_input_tokens'],
            session_state['total_output_tokens']
        )
        console.print(f"  Estimated cost: ${cost:.4f}")
    except Exception:
        pass
    
    # Show conversation history size
    history_len = len(session_state['conversation_history'])
    console.print(f"  History turns:  {history_len}")
    console.print("")

def _handle_compact_command(self, console, session_state):
    """
    Handle /compact command - compress conversation history.
    
    Inspired by Claude Code's /compact and Gemini CLI's /compress.
    Uses LLM to summarize older conversation turns while keeping recent ones.
    """
    history = session_state['conversation_history']
    
    if len(history) < 4:
        console.print("[yellow]Not enough conversation history to compact (need at least 4 turns)[/yellow]")
        return
    
    console.print("[dim]Compacting conversation history...[/dim]")
    
    try:
        from praisonaiagents import Agent
        
        # Keep the last 2 turns (4 messages: 2 user + 2 assistant)
        keep_count = 4
        to_compress = history[:-keep_count] if len(history) > keep_count else []
        to_keep = history[-keep_count:] if len(history) > keep_count else history
        
        if not to_compress:
            console.print("[yellow]Not enough old history to compress[/yellow]")
            return
        
        # Format history for summarization
        history_text = ""
        for i, msg in enumerate(to_compress):
            role = msg.get('role', 'unknown')
            content = msg.get('content', '')
            if len(content) > 500:
                content = content[:500] + "..."
            history_text += f"{role}: {content}\n\n"
        
        # Create summarization prompt
        summary_prompt = f"""Summarize the following conversation history into a concise state snapshot.
Focus on:
- Key facts and decisions made
- Important context that should be remembered
- Any ongoing tasks or goals

Conversation to summarize:
{history_text}

Provide a concise summary (max 200 words):"""
        
        # Use a lightweight agent for summarization
        summarizer = Agent(
            name="Summarizer",
            role="Conversation Summarizer",
            goal="Create concise summaries of conversations",
            backstory="You summarize conversations while preserving key information.",
            output="minimal",
            llm=session_state['current_model']
        )
        
        summary = summarizer.chat(summary_prompt, stream=False)
        
        # Replace old history with summary + recent turns
        new_history = [
            {"role": "system", "content": f"[Previous conversation summary]: {summary}"},
            *to_keep
        ]
        
        old_count = len(history)
        session_state['conversation_history'] = new_history
        new_count = len(new_history)
        
        console.print(f"[green]✓ Compacted {old_count} turns → {new_count} turns[/green]")
        console.print(f"[dim]Summary: {str(summary)[:100]}...[/dim]")
        
    except Exception as e:
        console.print(f"[red]Error compacting: {e}[/red]")

def _handle_context_command(self, console, args, session_state):
    """
    Handle /context command - manage context budgeting and monitoring.
    
    Usage:
    - /context              - Show context stats
    - /context show         - Show summary + budgets
    - /context stats        - Token ledger table
    - /context budget       - Budget allocation details
    - /context dump         - Write snapshot now
    - /context on           - Enable monitoring
    - /context off          - Disable monitoring
    - /context path <path>  - Set snapshot path
    - /context format <fmt> - Set format (human/json)
    - /context frequency <f>- Set frequency
    - /context compact      - Trigger optimization
    """
    try:
        from ..features.context_manager import (
            handle_context_command,
            ContextManagerHandler,
        )
        
        # Get or create context manager
        context_manager = session_state.get("context_manager")
        if context_manager is None:
            context_manager = ContextManagerHandler(
                model=session_state.get("current_model", "gpt-4o-mini"),
                session_id=session_state.get("session_id", ""),
            )
            session_state["context_manager"] = context_manager
        
        handle_context_command(console, args, session_state, context_manager)
        
    except Exception as e:
        console.print(f"[red]Error handling context command: {e}[/red]")

def _worker_busy(self, session_state):
    """Return True if the execution worker is processing or has queued work.

    Used to gate workspace-mutating rollbacks (/undo, /revert) so a restore
    never races a turn that is still writing files.
    """
    worker_state = session_state.get('worker_state') or {}
    queue = session_state.get('execution_queue')
    lock = session_state.get('processing_lock')

    def _check():
        if worker_state.get('current_task') is not None:
            return True
        try:
            if queue is not None and queue.qsize() > 0:
                return True
        except Exception:
            pass
        return False

    # Read current_task and queue size under the same lock the worker holds
    # when it dequeues and publishes current_task. This guarantees we never
    # observe the gap between get() (item leaves the queue) and the
    # current_task assignment, where a turn is in-flight but invisible.
    if lock is not None:
        with lock:
            return _check()
    return _check()

def _handle_undo_command(self, console, session_state):
    """
    Handle /undo command - undo the last response.
    
    Inspired by Codex CLI's /undo and Gemini CLI's /restore.
    Removes the last user prompt and assistant response from history.
    """
    history = session_state['conversation_history']
    undo_stack = session_state['undo_stack']
    
    if len(history) < 2:
        console.print("[yellow]Nothing to undo[/yellow]")
        return

    # If auto-checkpointing is active, /undo also rolls the workspace files
    # back to the pre-turn checkpoint. In that case the worker-busy check
    # MUST run *before* we mutate conversation_history: otherwise a turn that
    # is still writing files would leave history changed while the workspace
    # is untouched (and the running turn could then append its own result),
    # putting history and files permanently out of sync.
    ckpt = session_state.get('session_checkpoints')
    rollback_enabled = (
        ckpt is not None and getattr(ckpt, 'enabled', False) and ckpt.turns
    )
    if rollback_enabled and _worker_busy(self, session_state):
        console.print(
            "[yellow]A turn is still running; nothing undone.[/yellow] "
            "Wait for it to finish (/status), then retry /undo."
        )
        return
    
    # Remove last assistant response and user prompt
    if len(history) >= 2:
        removed_assistant = history.pop()
        removed_user = history.pop()
        
        # Store in undo stack for potential redo
        undo_stack.append((removed_user, removed_assistant))
        
        console.print("[green]✓ Undone last turn[/green]")
        console.print(f"[dim]Removed: {str(removed_user.get('content', ''))[:50]}...[/dim]")

        # Roll the workspace files back to the pre-turn checkpoint so /undo
        # is a true safety net, not just a conversation-history edit. The
        # worker-busy gate was already checked above before mutating history.
        if rollback_enabled:
            console.print("[dim]Reverting workspace files to the previous checkpoint...[/dim]")
            ckpt.preview(1)
            restored = ckpt.revert(1)
            if restored:
                console.print(f"[green]✓ Workspace restored to {restored.short_id}[/green]")
            else:
                console.print("[yellow]No workspace checkpoint to restore[/yellow]")
    else:
        console.print("[yellow]Not enough history to undo[/yellow]")

def _handle_revert_command(self, console, args, session_state):
    """
    Handle /revert [n] - roll the workspace back n turns (default 1).

    Shows the diff that would be undone, then restores the files via the
    session checkpoint timeline. Requires auto-checkpointing to be active
    (checkpoints.auto in config or PRAISONAI_CHECKPOINTS=on).
    """
    ckpt = session_state.get('session_checkpoints')
    if ckpt is None or not getattr(ckpt, 'enabled', False):
        console.print(
            "[yellow]Workspace checkpointing is disabled.[/yellow] "
            "Enable it with [cyan]checkpoints.auto: true[/cyan] in config "
            "or [cyan]PRAISONAI_CHECKPOINTS=on[/cyan]."
        )
        return

    if not ckpt.turns:
        console.print("[yellow]No checkpoints to revert to[/yellow]")
        return

    if _worker_busy(self, session_state):
        console.print(
            "[yellow]A turn is still running.[/yellow] "
            "Reverting now could race the agent's file writes — wait for it "
            "to finish (check /status), then retry /revert."
        )
        return

    n = 1
    if args:
        try:
            n = int(str(args).strip())
        except ValueError:
            console.print("[yellow]Usage: /revert [n][/yellow]")
            return

    if n < 1 or n > len(ckpt.turns):
        console.print(
            f"[yellow]Can only revert 1..{len(ckpt.turns)} turn(s)[/yellow]"
        )
        return

    console.print(f"[dim]Changes that will be undone (last {n} turn(s)):[/dim]")
    ckpt.preview(n)
    restored = ckpt.revert(n)
    if restored:
        console.print(
            f"[green]✓ Workspace reverted to {restored.short_id}[/green] "
            f"[dim]({restored.message})[/dim]"
        )
    else:
        console.print("[yellow]Failed to revert workspace[/yellow]")

def _handle_queue_command(self, console, args, session_state):
    """
    Handle /queue command - show or manage message queue.
    
    Usage:
    - /queue       - Show queued messages
    - /queue clear - Clear the queue
    - /queue remove N - Remove message at index N
    """
    message_queue = session_state.get('message_queue')
    state_manager = session_state.get('state_manager')
    queue_display = session_state.get('queue_display')
    
    if not message_queue:
        console.print("[yellow]Message queue not initialized[/yellow]")
        return
    
    args = args.strip().lower() if args else ""
    
    if args == "clear":
        count = message_queue.count
        message_queue.clear()
        console.print(f"[green]✓ Cleared {count} queued message(s)[/green]")
    elif args.startswith("remove "):
        try:
            index = int(args.split()[1])
            removed = message_queue.remove_at(index)
            if removed:
                console.print(f"[green]✓ Removed: {removed[:50]}...[/green]")
            else:
                console.print(f"[yellow]Invalid index: {index}[/yellow]")
        except (ValueError, IndexError):
            console.print("[yellow]Usage: /queue remove <index>[/yellow]")
    else:
        # Show queue status
        if state_manager:
            status = queue_display.format_status() if queue_display else ""
            if status:
                console.print(f"[cyan]{status}[/cyan]")
        
        if message_queue.is_empty:
            console.print("[dim]No messages in queue[/dim]")
        else:
            console.print(f"\n[bold cyan]Queued Messages ({message_queue.count}):[/bold cyan]")
            for i, msg in enumerate(message_queue.get_all()):
                display_msg = msg[:60] + "..." if len(msg) > 60 else msg
                console.print(f"  {i}. ↳ {display_msg}")
            console.print("\n[dim]Use /queue clear to clear, /queue remove N to remove[/dim]")

def _run_chat_mode(self, prompt, args):
    """
    Run a single prompt in interactive style (non-interactive mode for testing).
    
    Usage: praisonai "your prompt" --chat
           praisonai "your prompt" --chat-mode  (alias)
    
    This runs the prompt using the same agent/tools as interactive mode
    but exits after one response (useful for testing and scripting).
    """
    from rich.console import Console
    
    console = Console()
    # Persist the caller's args (e.g. from `praisonai code`) so the
    # agent-creation path can read the named-agent profile, approval config,
    # and reasoning effort via self.args. Without this the --agent/--thinking
    # flags resolved in code.py are silently dropped.
    if args is not None:
        self.args = args
    self._interactive_mode = True  # Use interactive mode settings
    
    # Load tools
    tools_list = _load_interactive_tools(self, )
    
    console.print(f"[dim]Chat mode: {len(tools_list)} tools available[/dim]")
    console.print(f"[dim]Prompt: {prompt[:50]}{'...' if len(prompt) > 50 else ''}[/dim]\n")
    
    # Process the prompt with profiling enabled for testing
    _process_interactive_prompt(self, prompt, tools_list, console, show_profiling=True)
    
    return None

def _start_execution_worker(self, tools_list, console, session_state):
    """
    Start the background execution worker thread.
    
    This worker continuously processes messages from the queue,
    allowing the main input loop to remain non-blocking.
    """
    import threading
    import time
    import sys
    import queue as queue_module
    from rich.panel import Panel
    from ..features.message_queue import ProcessingState
    
    state_manager = session_state['state_manager']
    message_queue = session_state['message_queue']
    live_status = session_state['live_status']
    execution_queue = session_state['execution_queue']
    approval_request_queue = session_state['approval_request_queue']
    approval_response_queue = session_state['approval_response_queue']
    worker_state = session_state['worker_state']
    # Shared with _worker_busy() so dequeue+publish of current_task is
    # atomic w.r.t. the rollback gate (no lock -> fall back to a private one).
    processing_lock = session_state.get('processing_lock') or threading.Lock()
    
    # Check if trust mode is enabled (via --trust flag or PRAISON_APPROVAL_MODE=auto env var)
    trust_mode = getattr(self.args, 'trust', False) if hasattr(self, 'args') else False
    approval_mode_env = os.environ.get("PRAISON_APPROVAL_MODE", "").lower()
    if approval_mode_env == "auto":
        trust_mode = True
    
    def worker_loop():
        """Main worker loop - processes execution queue."""
        while worker_state['running']:
            try:
                # Dequeue and publish current_task atomically under the
                # shared processing_lock so _worker_busy() can never observe
                # the gap between get() (which makes the item invisible to
                # qsize()) and the current_task assignment. We use a
                # non-blocking get_nowait() inside the lock instead of a
                # blocking get(timeout=...) so the lock is held only for the
                # microsecond-scale dequeue+publish, never across the poll
                # wait (which would stall the rollback gate for up to 0.5s).
                task = None
                with processing_lock:
                    try:
                        task = execution_queue.get_nowait()
                        worker_state['current_task'] = task
                    except queue_module.Empty:
                        task = None
                if task is None:
                    # No work right now; sleep briefly to avoid busy-spin,
                    # then re-check the running flag and the queue.
                    time.sleep(0.05)
                    continue

                # Extract task context
                prompt = task.get('prompt', '')
                task_id = task.get('task_id', 0)
                question = task.get('question', prompt)
                start_time = time.time()
                
                # Set processing state with full task context
                state_manager.set_state(ProcessingState.PROCESSING)
                task['status'] = 'running'
                task['start_time'] = start_time
                live_status.clear()
                live_status.update_status(f"Task #{task_id}: Thinking...")
                
                try:
                    from praisonaiagents import Agent
                    import logging
                    import warnings
                    
                    # Suppress noisy loggers
                    for logger_name in ["httpx", "httpcore", "duckduckgo_search", "crawl4ai"]:
                        logging.getLogger(logger_name).setLevel(logging.WARNING)
                    
                    # Set up approval callback
                    try:
                        from praisonaiagents.approval import set_approval_callback, ApprovalDecision
                        
                        if trust_mode:
                            def auto_approve_all(function_name, arguments, risk_level):
                                return ApprovalDecision(approved=True, reason="Auto-approved via --trust flag")
                            set_approval_callback(auto_approve_all)
                        else:
                            def interactive_approval_callback(function_name, arguments, risk_level):
                                """Request approval from main thread via queue."""
                                approval_request_queue.put({
                                    'function_name': function_name,
                                    'arguments': arguments,
                                    'risk_level': risk_level
                                })
                                worker_state['approval_pending'] = True
                                
                                try:
                                    response = approval_response_queue.get(timeout=120)
                                    worker_state['approval_pending'] = False
                                    return response
                                except queue_module.Empty:
                                    worker_state['approval_pending'] = False
                                    return ApprovalDecision(approved=False, reason="Approval timeout")
                            
                            set_approval_callback(interactive_approval_callback)
                    except ImportError:
                        pass
                    
                    with warnings.catch_warnings():
                        warnings.filterwarnings("ignore")
                        
                        model = session_state.get('current_model')
                        conversation_history = session_state.get('conversation_history', [])
                        
                        live_status.update_status("Creating agent...")
                        
                        # Build backstory with context
                        backstory = "You are a helpful AI assistant with access to tools for file operations, code intelligence, and shell commands."

                        # Auto-load AGENTS.md/CLAUDE.md project context (unless --no-context)
                        if not getattr(getattr(self, 'args', None), 'no_context', False):
                            project_context = _load_cli_project_context(self)
                            if project_context:
                                backstory += "\n\n# Project Context\n" + project_context

                        if conversation_history:
                            recent = conversation_history[-10:]
                            context_lines = []
                            for msg in recent:
                                role = msg.get('role', 'unknown')
                                content = msg.get('content', '')[:200]
                                context_lines.append(f"{role}: {content}")
                            if context_lines:
                                backstory += "\n\nRecent conversation context:\n" + "\n".join(context_lines)
                        
                        agent = Agent(
                            name="Assistant",
                            role="Helpful AI Assistant",
                            goal="Help the user with their tasks",
                            backstory=backstory,
                            tools=tools_list if tools_list else None,
                            output="minimal",
                            llm=model
                        )
                        
                        live_status.update_status(f"Task #{task_id}: Calling LLM...")
                        
                        response = agent.chat(prompt, stream=False)
                        response_str = str(response) if response else ""
                        
                        # Calculate elapsed time
                        elapsed = time.time() - start_time
                        
                        # Store completed task for display with Q/A mapping
                        completed_task = {
                            'task_id': task_id,
                            'question': task.get('question', prompt),
                            'response': response_str,
                            'elapsed': elapsed,
                            'status': 'completed',
                        }
                        worker_state['completed_tasks'].append(completed_task)
                        
                        # Update session state
                        input_tokens = len(prompt) // 4
                        output_tokens = len(response_str) // 4
                        session_state['total_input_tokens'] += input_tokens
                        session_state['total_output_tokens'] += output_tokens
                        session_state['request_count'] += 1
                        session_state['conversation_history'].append({'role': 'user', 'content': prompt})
                        session_state['conversation_history'].append({'role': 'assistant', 'content': response_str})
                        
                        # Persist to UnifiedSession
                        if 'unified_session' in session_state and 'session_store' in session_state:
                            unified_session = session_state['unified_session']
                            unified_session.add_user_message(prompt)
                            unified_session.add_assistant_message(response_str)
                            unified_session.update_stats(input_tokens, output_tokens)
                            session_state['session_store'].save(unified_session)
                
                except Exception as e:
                    # Store error task for display with Q/A mapping
                    error_task = {
                        'task_id': task_id,
                        'question': task.get('question', prompt),
                        'error': str(e),
                        'status': 'failed',
                    }
                    worker_state['error_tasks'].append(error_task)
                
                finally:
                    worker_state['current_task'] = None
                    worker_state['tool_activity'] = None
                    state_manager.set_state(ProcessingState.IDLE)
                    live_status.clear()
                    execution_queue.task_done()
            
            except Exception as e:
                import traceback
                traceback.print_exc()
    
    # Start worker thread
    worker_thread = threading.Thread(target=worker_loop, daemon=True, name="ExecutionWorker")
    worker_thread.start()
    return worker_thread

def _submit_prompt_to_worker(self, prompt, session_state):
    """
    Submit a prompt to the execution worker queue.
    
    This is NON-BLOCKING - returns immediately after queuing.
    """
    execution_queue = session_state['execution_queue']
    execution_queue.put({'prompt': prompt})

def _process_interactive_prompt(self, prompt, tools_list, console, show_profiling=False, session_state=None):
    """Process a prompt in interactive mode with streaming."""
    from rich.live import Live
    from rich.spinner import Spinner
    import sys
    import warnings
    import logging
    import time
    
    # Profiling timestamps
    timings = {}
    timings['start'] = time.time()
    
    # Store original log levels to restore later (no global impact)
    original_levels = {}
    loggers_to_suppress = ["httpx", "httpcore", "duckduckgo_search", "crawl4ai", "lib"]
    for logger_name in loggers_to_suppress:
        logger = logging.getLogger(logger_name)
        original_levels[logger_name] = logger.level
        logger.setLevel(logging.WARNING)
    
    # Temporarily filter warnings (scoped to this function)
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message=".*duckduckgo_search.*")
        warnings.filterwarnings("ignore", message=".*has been renamed.*")
    
    try:
        # Import agent
        timings['import_start'] = time.time()
        from praisonaiagents import Agent
        timings['import_end'] = time.time()
        
        # Set up auto-approval if PRAISON_APPROVAL_MODE=auto
        approval_mode_env = os.environ.get("PRAISON_APPROVAL_MODE", "").lower()
        trust_mode = getattr(self.args, 'trust', False) if hasattr(self, 'args') else False
        if approval_mode_env == "auto" or trust_mode:
            try:
                from praisonaiagents.approval import set_approval_callback, ApprovalDecision
                def auto_approve_all(function_name, arguments, risk_level):
                    return ApprovalDecision(approved=True, reason="Auto-approved via PRAISON_APPROVAL_MODE=auto")
                set_approval_callback(auto_approve_all)
            except ImportError:
                pass
        
        # Determine model to use
        model = None
        if session_state and session_state.get('current_model'):
            model = session_state['current_model']
        elif hasattr(self, 'args') and getattr(self.args, 'llm', None):
            model = self.args.llm
        
        # Optional named-agent profile (tools + permission scope) and
        # reasoning effort, surfaced by `praisonai code --agent/--thinking`.
        agent_kwargs = {}
        agent_profile = getattr(self.args, 'agent_profile', None) if hasattr(self, 'args') else None
        if agent_profile and agent_profile.get('tools'):
            # The profile's tools replace the default tool set so the
            # least-privilege scope is honoured (e.g. read-only profiles).
            tools_list = agent_profile['tools']
        agent_approval = getattr(self.args, 'agent_approval', None) if hasattr(self, 'args') else None
        if agent_approval is not None:
            agent_kwargs['approval'] = agent_approval
        thinking_budget = getattr(self.args, 'thinking_budget', None) if hasattr(self, 'args') else None

        # Show thinking indicator and create agent
        timings['agent_create_start'] = time.time()
        with Live(Spinner("dots", text="Thinking...", style="cyan"), console=console, refresh_per_second=10, transient=True):
            # Create agent with tools
            agent = Agent(
                name="Assistant",
                role="Helpful AI Assistant", 
                goal="Help the user with their tasks",
                backstory="You are a helpful AI assistant with access to tools for file operations, shell commands, and web search. Use tools when needed to complete tasks.",
                tools=tools_list if tools_list else None,
                output="minimal",  # Suppress verbose panels
                llm=model,
                **agent_kwargs,
            )
            # Reasoning effort is applied via the property setter (not a
            # constructor kwarg) to keep defaults byte-for-byte when omitted.
            if thinking_budget is not None:
                agent.thinking_budget = thinking_budget
        timings['agent_create_end'] = time.time()
        
        # Get response
        console.print()  # New line before response
        
        timings['llm_start'] = time.time()
        
        # Use chat method (streaming is handled internally by verbose mode)
        response = agent.chat(prompt, stream=False)
        
        timings['llm_end'] = time.time()
        
        # Check if tools were used by looking at agent's tool execution history
        if hasattr(agent, '_tool_calls') and agent._tool_calls:
            for tool_call in agent._tool_calls:
                tool_name = tool_call.get('name', 'unknown')
                console.print(f"[dim]⚙ Used tool: {tool_name}[/dim]")
        
        # Print response with simulated streaming effect
        timings['display_start'] = time.time()
        response_str = str(response) if response else ""
        if response_str:
            words = response_str.split()
            for i, word in enumerate(words):
                console.print(word + " ", end="")
                sys.stdout.flush()
                if i % 15 == 14:  # Small pause every 15 words for streaming effect
                    time.sleep(0.005)
            console.print()  # Final newline
        timings['display_end'] = time.time()
        
        # Update session state with token estimates and history
        if session_state is not None:
            # Estimate tokens (rough: ~4 chars per token)
            input_tokens = len(prompt) // 4
            output_tokens = len(response_str) // 4
            
            session_state['total_input_tokens'] += input_tokens
            session_state['total_output_tokens'] += output_tokens
            session_state['request_count'] += 1
            
            # Add to conversation history
            session_state['conversation_history'].append({
                'role': 'user',
                'content': prompt
            })
            session_state['conversation_history'].append({
                'role': 'assistant',
                'content': response_str
            })
            
            # Persist to UnifiedSession
            if 'unified_session' in session_state and 'session_store' in session_state:
                unified_session = session_state['unified_session']
                unified_session.add_user_message(prompt)
                unified_session.add_assistant_message(response_str)
                unified_session.update_stats(input_tokens, output_tokens)
                session_state['session_store'].save(unified_session)
        
        # Show profiling if enabled
        if show_profiling:
            timings['total'] = time.time() - timings['start']
            console.print("\n[dim]─── Profiling ───[/dim]")
            console.print(f"[dim]Import:      {(timings['import_end'] - timings['import_start'])*1000:.1f}ms[/dim]")
            console.print(f"[dim]Agent setup: {(timings['agent_create_end'] - timings['agent_create_start'])*1000:.1f}ms[/dim]")
            console.print(f"[dim]LLM call:    {(timings['llm_end'] - timings['llm_start'])*1000:.1f}ms[/dim]")
            console.print(f"[dim]Display:     {(timings['display_end'] - timings['display_start'])*1000:.1f}ms[/dim]")
            console.print(f"[dim]Total:       {timings['total']*1000:.1f}ms[/dim]")
        
    except Exception as e:
        console.print(f"\n[red]Error: {e}[/red]")
        import traceback
        traceback.print_exc()
    finally:
        # Restore original log levels (no global impact on main package)
        for logger_name, level in original_levels.items():
            logging.getLogger(logger_name).setLevel(level)
