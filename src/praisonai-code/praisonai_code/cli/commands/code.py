"""
Code command group for PraisonAI CLI.

Provides terminal-native code assistant mode.
This command NEVER opens a browser - it runs entirely in the terminal.
"""

from typing import List, Optional

import typer

app = typer.Typer(help="Terminal-native code assistant mode")


@app.callback(invoke_without_command=True)
def code_main(
    ctx: typer.Context,
    prompt: Optional[str] = typer.Argument(None, help="Code task or question"),
    model: Optional[str] = typer.Option(None, "--model", "-m", help="LLM model to use"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output"),
    tools: Optional[str] = typer.Option(None, "--tools", "-t", help="Tools file path"),
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w", help="Workspace directory"),
    file: Optional[List[str]] = typer.Option(None, "--file", "-f", help="Attach file(s) to context"),
    no_acp: bool = typer.Option(False, "--no-acp", help="Disable ACP tools (file operations)"),
    no_lsp: bool = typer.Option(False, "--no-lsp", help="Disable LSP tools (code intelligence)"),
    safe_mode: bool = typer.Option(True, "--safe/--no-safe", help="Safe mode (default ON): require approval for file writes and commands"),
    dangerously_skip_approval: bool = typer.Option(False, "--dangerously-skip-approval", help="Skip all approval prompts and run dangerous tools unguarded (restores legacy behaviour)"),
    checkpoints: bool = typer.Option(False, "--checkpoints/--no-checkpoints", help="Auto-checkpoint the workspace before each file-mutating turn (enables in-session /undo and /revert)"),
    revert: Optional[str] = typer.Option(None, "--revert", help="Restore the workspace to a prior checkpoint (id, short id, or 'last') and exit"),
    session_id: Optional[str] = typer.Option(None, "--session", "-s", help="Session ID to resume"),
    continue_session: bool = typer.Option(False, "--continue", "-c", help="Continue last session"),
    agent: Optional[str] = typer.Option(None, "--agent", "-a", help="Use a named custom agent profile (applies its tools and permission/mode scope)"),
    thinking: Optional[str] = typer.Option(None, "--thinking", help="Reasoning effort (off, minimal, low, medium, high)"),
    autonomy: bool = typer.Option(True, "--autonomy/--no-autonomy", help="Enable agent autonomy for complex tasks"),
    profile: bool = typer.Option(False, "--profile", help="Enable CLI profiling (timing breakdown)"),
    profile_deep: bool = typer.Option(False, "--profile-deep", help="Enable deep profiling (cProfile stats, higher overhead)"),
):
    """
    Start terminal-native code assistant mode.
    
    This is a terminal-based code assistant with file awareness, diff display,
    and ACP/LSP tools enabled by default. It NEVER opens a browser.
    
    For browser-based code UI, use: praisonai ui code
    
    Examples:
        praisonai code
        praisonai code "Refactor this function"
        praisonai code --model gpt-4o --workspace ./src
        praisonai code "Fix the bug" --file main.py
        praisonai code "What is 2+2?" --profile
    """
    import os
    import argparse
    
    # Validate --thinking up front so an unknown value fails closed before any
    # work is done (consistent with MODE_RULES validation on custom agents).
    from praisonai.cli.features.thinking import thinking_to_budget
    try:
        thinking_budget = thinking_to_budget(thinking)
    except ValueError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(1)

    # Resolve a named agent profile (tools + permission/mode scope). The profile
    # reuses the same custom-definitions loader as `praisonai run --agent`, so a
    # profile defined once in .praisonai/agents/<name>.md behaves identically
    # across `code`, `run`, and the Python Agent(...) constructor.
    agent_profile = None
    if agent:
        from praisonai.cli.features.custom_definitions import load_agent_from_name
        agent_profile = load_agent_from_name(agent)
        if not agent_profile:
            typer.echo(f"Error: Agent '{agent}' not found", err=True)
            raise typer.Exit(1)

    # Set workspace if provided
    if workspace:
        os.environ["PRAISONAI_WORKSPACE"] = workspace

    # --revert: restore the workspace to a prior checkpoint and exit before
    # starting a session. Reuses the existing CheckpointsHandler so the same
    # 'last'/short-id/prefix resolution as `praisonai checkpoint restore`
    # applies. This is a one-shot CLI path, not the interactive /revert.
    if revert is not None:
        _revert_workspace(revert, workspace or os.getcwd(), verbose)
        return

    # --checkpoints opts the session into turn-aware auto-checkpointing,
    # surfaced to the interactive loop via the env override the session
    # checkpoint manager reads. Default off keeps zero overhead.
    if checkpoints:
        os.environ["PRAISONAI_CHECKPOINTS"] = "on"

    # Enable code-specific environment
    os.environ["PRAISONAI_CODE_MODE"] = "true"
    
    # Set approval mode based on --safe flag.
    # Safe-by-default: dangerous tools (shell exec, file writes) are gated
    # behind an interactive approval prompt unless the user explicitly opts
    # out with --no-safe or --dangerously-skip-approval. The latter also sets
    # PRAISONAI_TOOL_SAFETY=off so the core runtime skips its safe-by-default
    # ask path (see Agent.__init__ approval handling).
    if dangerously_skip_approval or not safe_mode:
        os.environ["PRAISON_APPROVAL_MODE"] = "auto"
        os.environ["PRAISONAI_TOOL_SAFETY"] = "off"
    else:
        os.environ["PRAISON_APPROVAL_MODE"] = "prompt"
        # Clear any stale bypass from a previous --no-safe run in the same
        # process (REPL/worker/test). Leaving PRAISONAI_TOOL_SAFETY=off would
        # silently keep later safe-default agents unguarded.
        os.environ.pop("PRAISONAI_TOOL_SAFETY", None)
    
    # Handle profiling for single prompt mode
    if prompt and (profile or profile_deep):
        _run_profiled_code(
            prompt=prompt,
            model=model,
            verbose=verbose,
            profile_deep=profile_deep,
            thinking_budget=thinking_budget,
        )
        return
    
    # Warn if profiling requested without prompt (REPL mode doesn't support profiling)
    if (profile or profile_deep) and not prompt:
        typer.echo("⚠️  Profiling is only supported for single prompt mode.", err=True)
        typer.echo("   Use: praisonai code \"your prompt\" --profile", err=True)
    
    # Build args namespace for _start_interactive_mode
    args = argparse.Namespace()
    args.llm = model
    args.verbose = verbose
    args.tools = tools
    args.no_acp = no_acp
    args.no_lsp = no_lsp
    args.resume_session = session_id if session_id else ('last' if continue_session else None)
    # Reasoning effort (mapped to the core thinking_budget) and named agent
    # profile (tools + permission/mode scope), consumed when the agent is built.
    args.thinking_budget = thinking_budget
    args.agent_profile = agent_profile

    # Resolve the named profile's permission/mode scope into an approval config
    # so the code session runs least-privilege (e.g. `--agent plan` is rejected
    # for write/edit/shell). Reuses the same engine as `praisonai run --agent`.
    args.agent_approval = None
    if agent_profile:
        permission_config = agent_profile.get("permissions")
        if permission_config:
            from praisonai.cli.features.approval import resolve_approval_config
            has_ask_rules = any(
                str(action).strip().lower() == "ask"
                for action in permission_config.values()
            )
            args.agent_approval = resolve_approval_config(
                "console",
                non_interactive=not has_ask_rules,
                permissions_config=permission_config,
            )
        # Apply the profile's model unless the user overrode it with --model.
        if not model and agent_profile.get("llm"):
            args.llm = agent_profile["llm"]
    
    # Import and run the terminal-native interactive mode
    from praisonai.cli.main import PraisonAI
    
    praison = PraisonAI()
    
    if prompt:
        # Single prompt mode - use _run_chat_mode with code context
        praison._run_chat_mode(prompt, args)
    else:
        # Interactive REPL mode - use _start_interactive_mode
        praison._start_interactive_mode(args)


def _run_profiled_code(
    prompt: str,
    model: Optional[str] = None,
    verbose: bool = False,
    profile_deep: bool = False,
    thinking_budget: Optional[int] = None,
):
    """Run code assistant with profiling enabled."""
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
        "name": "CodeAgent",
        "role": "Code Assistant",
        "goal": "Help with coding tasks",
        "verbose": verbose,
    }
    if model:
        agent_config["llm"] = model
    
    agent = Agent(**agent_config)
    # thinking_budget is set post-construction via the property setter (the
    # Agent constructor does not accept it as a keyword argument).
    if thinking_budget is not None:
        agent.thinking_budget = thinking_budget
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


def _revert_workspace(ref: str, workspace: str, verbose: bool = False) -> None:
    """Restore the workspace to a checkpoint (one-shot ``code --revert``).

    Resolves ``ref`` ('last'/short id/prefix) the same way
    ``praisonai checkpoint restore`` does, previews the diff, then restores.
    """
    import asyncio

    from praisonai.cli.commands.checkpoint import _resolve_checkpoint_id
    from praisonai.cli.features.checkpoints import CheckpointsHandler

    # Honor a configured checkpoints.storage_dir so this one-shot restore reads
    # from the same store the interactive session writes to.
    storage_dir = None
    try:
        from ..configuration.resolver import resolve_config
        section = (resolve_config().extra or {}).get("checkpoints", {})
        if isinstance(section, dict):
            storage_dir = section.get("storage_dir")
    except Exception:
        storage_dir = None

    handler = CheckpointsHandler(
        workspace_dir=workspace, verbose=verbose, storage_dir=storage_dir
    )

    async def _run() -> bool:
        resolved = await _resolve_checkpoint_id(handler, ref)
        if resolved is None:
            handler._print_error(f"No checkpoint found for: {ref}")
            return False
        # Preview what restoring will change before applying it.
        await handler.diff(resolved, None)
        return await handler.restore(resolved)

    if not asyncio.run(_run()):
        raise typer.Exit(1)
