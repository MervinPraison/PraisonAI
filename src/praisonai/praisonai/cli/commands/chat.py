"""
Chat command group for PraisonAI CLI.

Provides terminal-native interactive chat mode.
This command NEVER opens a browser - it runs entirely in the terminal.
"""

from typing import List, Optional, Union

import typer

app = typer.Typer(help="Terminal-native interactive chat mode")


def _parse_memory_flag(memory: Optional[str], no_memory: bool) -> Union[bool, str, None]:
    """
    Parse memory CLI flag to value for Agent.
    
    Precedence: --no-memory > --memory=value > --memory (flag) > None
    
    Args:
        memory: Memory flag value (None, "true", preset string, or URL)
        no_memory: Whether --no-memory was specified
        
    Returns:
        - False if --no-memory
        - True if --memory (flag only)
        - str if --memory=preset or --memory=URL
        - None if neither specified
    """
    if no_memory:
        return False
    
    if memory is None:
        return None
    
    # --memory flag without value sets "true"
    if memory.lower() == "true":
        return True
    
    # --memory=false explicitly disables
    if memory.lower() == "false":
        return False
    
    # Otherwise it's a preset or URL string
    return memory


@app.callback(invoke_without_command=True)
def chat_main(
    ctx: typer.Context,
    prompt: Optional[str] = typer.Argument(None, help="Initial prompt for chat"),
    model: Optional[str] = typer.Option(None, "--model", "-m", help="LLM model to use"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output"),
    memory: Optional[str] = typer.Option(
        None, "--memory",
        help="Enable memory. Use --memory for default, --memory=redis for preset, --memory=postgresql://... for URL",
        is_flag=False,
        flag_value="true",
    ),
    no_memory: bool = typer.Option(False, "--no-memory", help="Disable memory"),
    tools: Optional[str] = typer.Option(None, "--tools", "-t", help="Tools file path"),
    user_id: Optional[str] = typer.Option(None, "--user-id", help="User ID for memory isolation"),
    session_id: Optional[str] = typer.Option(None, "--session", "-s", help="Session ID to resume"),
    continue_session: bool = typer.Option(False, "--continue", "-c", help="Continue last session"),
    file: Optional[List[str]] = typer.Option(None, "--file", "-f", help="Attach file(s) to prompt"),
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w", help="Workspace directory"),
    no_acp: bool = typer.Option(False, "--no-acp", help="Disable ACP tools"),
    no_lsp: bool = typer.Option(False, "--no-lsp", help="Disable LSP tools"),
    safe_mode: bool = typer.Option(False, "--safe", help="Safe mode: require approval for file writes and commands"),
    autonomy: bool = typer.Option(True, "--autonomy/--no-autonomy", help="Enable agent autonomy for complex tasks"),
    # NEW: Agent-like consolidated params for ALL GREEN consistency
    knowledge: Optional[str] = typer.Option(
        None, "--knowledge", "-k",
        help="Enable knowledge/RAG. Use --knowledge for default, --knowledge=docs/ for sources",
        is_flag=False,
        flag_value="true",
    ),
    guardrails: Optional[str] = typer.Option(
        None, "--guardrails",
        help="Enable guardrails. Use --guardrails for default, --guardrails=strict for preset",
        is_flag=False,
        flag_value="true",
    ),
    web: Optional[str] = typer.Option(
        None, "--web",
        help="Enable web search. Use --web for default, --web=duckduckgo for preset",
        is_flag=False,
        flag_value="true",
    ),
    reflection: Optional[str] = typer.Option(
        None, "--reflection",
        help="Enable self-reflection. Use --reflection for default, --reflection=thorough for preset",
        is_flag=False,
        flag_value="true",
    ),
    # NEW: Additional consolidated params for ALL GREEN feature parity
    planning: Optional[str] = typer.Option(
        None, "--planning",
        help="Enable planning mode. Use --planning for default, --planning=thorough for preset",
        is_flag=False,
        flag_value="true",
    ),
    context: Optional[str] = typer.Option(
        None, "--context",
        help="Enable context management. Use --context for default",
        is_flag=False,
        flag_value="true",
    ),
    output: Optional[str] = typer.Option(
        None, "--output", "-o",
        help="Output mode (default: actions). Options: actions, plain, verbose, json, silent",
    ),
    execution: Optional[str] = typer.Option(
        None, "--execution",
        help="Execution preset. Use --execution=fast, --execution=thorough, --execution=unlimited",
    ),
    hooks: Optional[str] = typer.Option(
        None, "--hooks",
        help="Hooks config file path for lifecycle callbacks",
    ),
    caching: Optional[str] = typer.Option(
        None, "--caching",
        help="Enable caching. Use --caching for default, --caching=redis for preset",
        is_flag=False,
        flag_value="true",
    ),
    profile: bool = typer.Option(False, "--profile", help="Enable CLI profiling (timing breakdown)"),
    profile_deep: bool = typer.Option(False, "--profile-deep", help="Enable deep profiling (cProfile stats, higher overhead)"),
    debug: bool = typer.Option(False, "--debug", help="Enable debug logging to ~/.praisonai/async_tui_debug.log"),
    # UI backend selection
    ui_backend: str = typer.Option("auto", "--ui-backend", help="UI backend: auto, plain, rich, mg (middle-ground)"),
    json_output: bool = typer.Option(False, "--json", help="Output JSON (forces plain backend)"),
    no_color: bool = typer.Option(False, "--no-color", help="Disable colors"),
    theme: str = typer.Option("default", "--theme", help="UI theme: default, dark, light, minimal"),
    compact: bool = typer.Option(False, "--compact", help="Compact output mode"),
):
    """
    Start terminal-native interactive chat mode.
    
    This is a terminal REPL with streaming responses, slash commands,
    and multi-turn conversation support. It NEVER opens a browser.
    
    For browser-based chat UI, use: praisonai ui chat
    
    Examples:
        praisonai chat
        praisonai chat "Hello, how are you?"
        praisonai chat --model gpt-4o --memory
        praisonai chat --continue  # Resume last session
        praisonai chat "Summarize this" --file README.md
        praisonai chat "What is 2+2?" --profile
    """
    import os
    
    # Set workspace if provided
    if workspace:
        os.environ["PRAISONAI_WORKSPACE"] = workspace
    
    # Handle profiling for single prompt mode
    if prompt and (profile or profile_deep):
        _run_profiled_chat(
            prompt=prompt,
            model=model,
            verbose=verbose,
            profile_deep=profile_deep,
        )
        return
    
    # Warn if profiling requested without prompt (REPL mode doesn't support profiling)
    if (profile or profile_deep) and not prompt:
        typer.echo("⚠️  Profiling is only supported for single prompt mode.", err=True)
        typer.echo("   Use: praisonai chat \"your prompt\" --profile", err=True)
    
    # Parse memory flag: --no-memory takes precedence, then --memory value
    # TODO: Pass memory_value to TUI when memory support is added
    _parse_memory_flag(memory, no_memory)
    
    # Set approval mode based on --safe flag
    import os
    if safe_mode:
        os.environ["PRAISON_APPROVAL_MODE"] = "prompt"
    else:
        os.environ["PRAISON_APPROVAL_MODE"] = "auto"
    
    # Use the async TUI (non-blocking, scrollable output)
    from praisonai.cli.interactive.async_tui import AsyncTUI, AsyncTUIConfig
    
    tui_config = AsyncTUIConfig(
        model=model or "gpt-4o-mini",
        show_logo=not compact,
        show_status_bar=not compact,
        session_id=session_id,
        workspace=workspace,
        debug=debug,
    )
    
    tui = AsyncTUI(config=tui_config)
    
    if prompt:
        # Single prompt mode - direct response, no streaming
        response = tui.run_single(prompt)
        if response:
            print(response)
    else:
        # Interactive split-pane TUI mode
        tui.run()


def _run_profiled_chat(
    prompt: str,
    model: Optional[str] = None,
    verbose: bool = False,
    profile_deep: bool = False,
):
    """Run chat with profiling enabled."""
    from praisonai.cli.features.cli_profiler import (
        CLIProfileConfig,
        CLIProfiler,
    )
    
    config = CLIProfileConfig(enabled=True, deep=profile_deep)
    profiler = CLIProfiler(config)
    
    if profile_deep:
        typer.echo("⚠️  Deep profiling enabled - this adds significant overhead", err=True)
    
    profiler.start()
    
    # Import phase
    profiler.mark_import_start()
    try:
        from praisonaiagents import Agent
    except ImportError:
        typer.echo("Error: praisonaiagents not installed", err=True)
        raise typer.Exit(1)
    profiler.mark_import_end()
    
    # Agent initialization phase
    profiler.mark_init_start()
    agent_config = {
        "name": "ChatAgent",
        "role": "Assistant",
        "goal": "Help the user",
    }
    if model:
        agent_config["llm"] = model
    
    agent = Agent(**agent_config)
    profiler.mark_init_end()
    
    # Execution phase
    profiler.mark_exec_start()
    response = agent.start(prompt)
    profiler.mark_exec_end()
    
    profiler.stop()
    
    # Print response
    if response:
        print(response)
    
    # Print profiling report
    profiler.print_report()


def _run_legacy_terminal_chat(
    prompt: Optional[str] = None,
    model: Optional[str] = None,
    verbose: bool = False,
    memory: bool = False,
    tools: Optional[str] = None,
    user_id: Optional[str] = None,
    session_id: Optional[str] = None,
    continue_session: bool = False,
    workspace: Optional[str] = None,
    no_acp: bool = False,
    no_lsp: bool = False,
):
    """Run terminal-native chat using legacy _start_interactive_mode."""
    import argparse
    
    # Build args namespace for _start_interactive_mode
    args = argparse.Namespace()
    args.llm = model
    args.verbose = verbose
    args.memory = memory
    args.tools = tools
    args.user_id = user_id
    args.resume_session = session_id if session_id else ('last' if continue_session else None)
    args.no_acp = no_acp
    args.no_lsp = no_lsp
    
    # Import and run the terminal-native interactive mode
    from praisonai.cli.main import PraisonAI
    
    praison = PraisonAI()
    
    if prompt:
        # Single prompt mode - use _run_chat_mode
        praison._run_chat_mode(prompt, args)
    else:
        # Interactive REPL mode - use _start_interactive_mode
        praison._start_interactive_mode(args)
