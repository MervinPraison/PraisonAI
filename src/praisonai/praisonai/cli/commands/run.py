"""
Run command group for PraisonAI CLI.

Provides agent execution commands.
"""

from typing import Any, Dict, Optional

import typer

from ..output.console import get_output_controller
from ..state.identifiers import get_current_context
from ..configuration.resolver import resolve_config

app = typer.Typer(help="Run agents")


def _check_api_key_available() -> bool:
    """
    Check if an API key is available from environment or stored credentials.
    
    Also injects stored credentials into environment if no env key is present.
    
    Returns:
        True if an API key is available, False otherwise
    """
    import os
    
    # Check all known provider env vars first
    known_keys = (
        "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GOOGLE_API_KEY",
        "GEMINI_API_KEY", "GROQ_API_KEY", "COHERE_API_KEY",
    )
    if any(os.environ.get(k) for k in known_keys):
        return True
    
    # Try to inject stored credentials into env, then re-check any known provider key
    try:
        from ...llm.credentials import inject_credentials_into_env
        inject_credentials_into_env()
    except ImportError:
        # Fallback if credential module not available
        pass

    # Check all known provider env vars after potential injection
    if any(os.environ.get(k) for k in known_keys):
        return True

    # Final check using LLM resolution with credential fallback
    try:
        from ...llm.credentials import resolve_llm_endpoint_with_credentials
        endpoint = resolve_llm_endpoint_with_credentials()
        return bool(endpoint.api_key)
    except ImportError:
        # Fallback to basic env check
        return bool(os.environ.get("OPENAI_API_KEY"))
    except Exception:
        return False


@app.callback(invoke_without_command=True)
def run_main(
    ctx: typer.Context,
    target: Optional[str] = typer.Argument(None, help="Agent file or prompt"),
    model: Optional[str] = typer.Option(None, "--model", "-m", help="LLM model to use"),
    framework: Optional[str] = typer.Option(None, "--framework", "-f", help="Framework: praisonai, crewai, autogen"),
    interactive: bool = typer.Option(False, "--interactive", "-i", help="Interactive mode"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output"),
    stream: bool = typer.Option(False, "--stream/--no-stream", help="Stream output (default: off for production use)"),
    trace: bool = typer.Option(False, "--trace", help="Enable tracing"),
    memory: bool = typer.Option(False, "--memory", help="Enable memory"),
    tools: Optional[str] = typer.Option(None, "--tools", "-t", help="Tools file path"),
    toolset: Optional[str] = typer.Option(None, "--toolset", help="Named toolset groups (comma-separated, e.g., web,files)"),
    max_tokens: int = typer.Option(16000, "--max-tokens", help="Maximum output tokens"),
    profile: bool = typer.Option(False, "--profile", help="Enable CLI profiling (timing breakdown)"),
    profile_deep: bool = typer.Option(False, "--profile-deep", help="Enable deep profiling (cProfile stats, higher overhead)"),
    output_mode: Optional[str] = typer.Option(None, "--output", "-o", help="Output mode: silent (default), actions, verbose, json, stream"),
    approval: Optional[str] = typer.Option(None, "--approval", help="Approval backend: console, slack, telegram, discord, webhook, http, agent, auto, none"),
    approve_all_tools: bool = typer.Option(False, "--approve-all-tools", help="Require approval for ALL tool calls, not just dangerous tools"),
    approval_timeout: Optional[str] = typer.Option(None, "--approval-timeout", help="Seconds to wait for approval. Use 'none' for indefinite wait"),
    no_rules: bool = typer.Option(False, "--no-rules", help="Disable auto-injection of project instruction files"),
    # Session continuity options
    continue_session: bool = typer.Option(False, "--continue", "-c", help="Continue the most recent session for this project"),
    session: Optional[str] = typer.Option(None, "--session", "-s", help="Resume a specific session ID"),
    fork: bool = typer.Option(False, "--fork", help="Fork from the specified session (requires --session)"),
    no_save: bool = typer.Option(False, "--no-save", help="Don't auto-save session after execution"),
    # Custom definitions
    agent: Optional[str] = typer.Option(None, "--agent", "-a", help="Use a named custom agent"),
    command: Optional[str] = typer.Option(None, "--command", help="Execute a named custom command"),
):
    """
    Run agents from a file or prompt.
    
    Examples:
        praisonai run agents.yaml
        praisonai run "What is the weather?"
        praisonai run "What is the weather?" --continue
        praisonai run "Add tests" --session abc123
        praisonai run agents.yaml --interactive
        praisonai run "What is 2+2?" --profile
    """
    output = get_output_controller()
    _ = get_current_context()  # Initialize context
    
    # Resolve configuration if model not explicitly provided
    if model is None:
        try:
            config = resolve_config()
            if config.agent.model:
                model = config.agent.model
                if verbose:
                    output.print_info(f"Using model from config: {model}")
        except (ValueError, OSError) as e:
            # Continue if config resolution fails, but log in verbose mode
            if verbose:
                output.print_info(f"Skipping config-based model fallback: {e}")
    
    # Validate session options
    if fork and not session:
        output.print_error("--fork requires --session to specify which session to fork from")
        raise typer.Exit(1)
    
    if continue_session and session:
        output.print_error("Cannot use both --continue and --session together")
        raise typer.Exit(1)
    
    # Handle custom agent or command
    if agent:
        from ..features.custom_definitions import load_agent_from_name
        agent_config = load_agent_from_name(agent)
        if not agent_config:
            output.print_error(f"Agent '{agent}' not found")
            raise typer.Exit(1)
        
        # Run with custom agent
        _run_custom_agent(
            agent_config,
            target or "",  # Use target as the prompt if provided
            model=model,
            verbose=verbose,
            stream=stream,
            trace=trace,
            memory=memory,
            tools=tools,
            toolset=toolset,
            max_tokens=max_tokens,
            output_mode=output_mode,
            continue_session=continue_session,
            session=session,
            fork=fork,
            no_save=no_save,
        )
        return
    
    if command:
        from ..features.custom_definitions import interpolate_command_template
        prompt = interpolate_command_template(command, target or "")
        if not prompt:
            output.print_error(f"Command '{command}' not found")
            raise typer.Exit(1)
        
        # Run the interpolated command as a prompt
        _run_prompt(
            prompt,
            model=model,
            verbose=verbose,
            stream=stream,
            trace=trace,
            memory=memory,
            tools=tools,
            toolset=toolset,
            max_tokens=max_tokens,
            output_mode=output_mode,
            approval=approval,
            approve_all_tools=approve_all_tools,
            approval_timeout=approval_timeout,
            no_rules=no_rules,
            continue_session=continue_session,
            session=session,
            fork=fork,
            no_save=no_save,
        )
        return
    
    if not target:
        output.print_panel(
            "Run agents from a file or prompt.\n\n"
            "Usage:\n"
            "  praisonai run agents.yaml\n"
            "  praisonai run \"What is the weather?\"\n"
            "  praisonai run \"What is the weather?\" --continue\n"
            "  praisonai run \"Add tests\" --session abc123\n"
            "  praisonai run agents.yaml --interactive\n"
            "  praisonai run --agent researcher \"Find info on X\"\n"
            "  praisonai run --command summarize \"Long text here\"\n\n"
            "Options:\n"
            "  --model, -m       LLM model to use\n"
            "  --framework, -f   Framework (praisonai, crewai, autogen)\n"
            "  --interactive, -i Interactive mode\n"
            "  --verbose, -v     Verbose output\n"
            "  --trace           Enable tracing\n"
            "  --memory          Enable memory\n"
            "  --continue, -c    Continue the most recent session\n"
            "  --session, -s     Resume a specific session ID\n"
            "  --fork            Fork from specified session\n"
            "  --no-save         Don't auto-save session\n"
            "  --agent, -a       Use a named custom agent\n"
            "  --command         Execute a named custom command",
            title="Run Command"
        )
        return
    
    # Emit start event
    output.emit_start(
        message=f"Starting run: {target[:50]}..." if len(target) > 50 else f"Starting run: {target}",
        data={
            "target": target,
            "model": model,
            "framework": framework,
        }
    )
    
    # Check if target is a file or prompt
    import os
    is_file = os.path.exists(target) and (target.endswith('.yaml') or target.endswith('.yml'))
    
    # Handle profiling
    if profile or profile_deep:
        if is_file:
            # Profiling for YAML file execution
            _run_from_file_profiled(
                target,
                model=model,
                framework=framework,
                verbose=verbose,
                profile_deep=profile_deep,
                continue_session=continue_session,
                session=session,
                fork=fork,
                no_save=no_save,
            )
        else:
            # Profiling for direct prompt
            _run_prompt_profiled(
                target,
                model=model,
                verbose=verbose,
                profile_deep=profile_deep,
                continue_session=continue_session,
                session=session,
                fork=fork,
                no_save=no_save,
            )
        return
    
    if is_file:
        # Run from file
        _run_from_file(
            target,
            model=model,
            framework=framework,
            interactive=interactive,
            verbose=verbose,
            stream=stream,
            trace=trace,
            memory=memory,
            tools=tools,
            max_tokens=max_tokens,
            output_mode=output_mode,
            continue_session=continue_session,
            session=session,
            fork=fork,
            no_save=no_save,
        )
    else:
        # Run as prompt
        _run_prompt(
            target,
            model=model,
            verbose=verbose,
            stream=stream,
            trace=trace,
            memory=memory,
            tools=tools,
            toolset=toolset,
            max_tokens=max_tokens,
            output_mode=output_mode,
            approval=approval,
            approve_all_tools=approve_all_tools,
            approval_timeout=approval_timeout,
            no_rules=no_rules,
            continue_session=continue_session,
            session=session,
            fork=fork,
            no_save=no_save,
        )


def _run_from_file(
    file_path: str,
    model: Optional[str] = None,
    framework: Optional[str] = None,
    interactive: bool = False,
    verbose: bool = False,
    stream: bool = True,
    trace: bool = False,
    memory: bool = False,
    tools: Optional[str] = None,
    max_tokens: int = 16000,
    output_mode: Optional[str] = None,
    continue_session: bool = False,
    session: Optional[str] = None,
    fork: bool = False,
    no_save: bool = False,
):
    """Run agents from a YAML file."""
    output = get_output_controller()
    
    # Preflight check for API key availability
    if not _check_api_key_available():
        output.print_error(
            "No API key configured. Run: praisonai auth login"
        )
        raise typer.Exit(1)
    
    try:
        # Use existing PraisonAI class
        from praisonai.cli.main import PraisonAI
        
        praison = PraisonAI(
            agent_file=file_path,
            framework=framework or "praisonai",
        )
        
        # Set model if provided
        if model:
            praison.config_list[0]['model'] = model
        
        # Handle session continuity for YAML files
        session_id = None
        auto_save_name = None
        
        if continue_session or session or fork:
            from ..state.project_sessions import get_project_session_store, find_last_session
            
            if continue_session:
                # Find last session for this project
                session_id = find_last_session()
                if session_id:
                    output.print_info(f"Continuing session: {session_id}")
                else:
                    output.print_warning("No previous sessions found. Starting new session.")
                    
            elif session:
                # Use specific session
                project_store = get_project_session_store()
                if project_store.session_exists(session):
                    session_id = session
                    output.print_info(f"Resuming session: {session_id}")
                else:
                    output.print_error(f"Session not found: {session}")
                    raise typer.Exit(1)
                
                # Handle forking
                if fork:
                    from praisonaiagents.session.hierarchy import HierarchicalSessionStore
                    from ..utils.project import get_project_sessions_dir
                    
                    # Create hierarchical store for forking
                    hierarchical_store = HierarchicalSessionStore(str(get_project_sessions_dir()))
                    forked_session_id = hierarchical_store.fork_session(session_id)
                    session_id = forked_session_id
                    output.print_info(f"Forked session {session} -> {forked_session_id}")
        
        # Enable auto-save if not disabled
        if not no_save:
            import uuid
            auto_save_name = session_id or "session-" + str(uuid.uuid4())[:8]
        
        # Create args-like object for session configuration
        if session_id or auto_save_name:
            class Args:
                pass
            
            args = Args()
            args.auto_save = auto_save_name
            args.resume_session = session_id
            args.cli_project_sessions = bool(session_id or auto_save_name)
            
            praison.args = args
        
        # Run
        result = praison.run()
        
        output.emit_result(
            message="Run completed",
            data={"result": str(result) if result else None}
        )
        
        if result:
            if not output.is_json_mode:
                output.print_success("Run completed")
    
    except Exception as e:
        output.emit_error(message=str(e))
        output.print_error(str(e))
        raise typer.Exit(1)


def _run_prompt(
    prompt: str,
    model: Optional[str] = None,
    verbose: bool = False,
    stream: bool = True,
    trace: bool = False,
    memory: bool = False,
    tools: Optional[str] = None,
    toolset: Optional[str] = None,
    max_tokens: int = 16000,
    output_mode: Optional[str] = None,
    approval: Optional[str] = None,
    approve_all_tools: bool = False,
    approval_timeout: Optional[str] = None,
    no_rules: bool = False,
    continue_session: bool = False,
    session: Optional[str] = None,
    fork: bool = False,
    no_save: bool = False,
):
    """Run a direct prompt."""
    output = get_output_controller()
    
    # Preflight check for API key availability
    if not _check_api_key_available():
        output.print_error(
            "No API key configured. Run: praisonai auth login"
        )
        raise typer.Exit(1)
    
    try:
        # Handle session continuity first (before any execution mode)
        from praisonai.cli.main import PraisonAI
        
        praison = PraisonAI()
        
        if model:
            praison.config_list[0]['model'] = model
        
        # Handle session continuity
        session_id = None
        auto_save_name = None
        
        if continue_session or session or fork:
            from ..state.project_sessions import get_project_session_store, find_last_session
            
            if continue_session:
                # Find last session for this project
                session_id = find_last_session()
                if session_id:
                    output.print_info(f"Continuing session: {session_id}")
                else:
                    output.print_warning("No previous sessions found. Starting new session.")
                    
            elif session:
                # Use specific session
                project_store = get_project_session_store()
                if project_store.session_exists(session):
                    session_id = session
                    output.print_info(f"Resuming session: {session_id}")
                else:
                    output.print_error(f"Session not found: {session}")
                    raise typer.Exit(1)
                
                # Handle forking
                if fork:
                    from praisonaiagents.session.hierarchy import HierarchicalSessionStore
                    from ..utils.project import get_project_sessions_dir
                    
                    # Create hierarchical store for forking
                    hierarchical_store = HierarchicalSessionStore(str(get_project_sessions_dir()))
                    forked_session_id = hierarchical_store.fork_session(session_id)
                    session_id = forked_session_id
                    output.print_info(f"Forked session {session} -> {forked_session_id}")

        # Enable auto-save if not disabled (for all runs, not just session continuity)
        if not no_save:
            import uuid
            auto_save_name = session_id or "session-" + str(uuid.uuid4())[:8]
        if output_mode == "actions":
            from praisonaiagents import Agent
            from ..state.project_sessions import build_cli_memory_config, apply_cli_session_continuity
            
            agent_config = {
                "name": "RunAgent",
                "role": "Assistant", 
                "goal": "Complete the task",
                "output": "actions",  # Use actions preset
            }
            if model:
                agent_config["llm"] = model
            
            # Resolve approval backend if specified
            if approval:
                from praisonai.cli.features.approval import resolve_approval_config
                agent_config["approval"] = resolve_approval_config(
                    approval, all_tools=approve_all_tools, timeout=approval_timeout,
                )
            
            memory_cfg = build_cli_memory_config(session_id, auto_save_name)
            if memory_cfg is not None:
                agent_config["memory"] = memory_cfg
            
            agent = Agent(**agent_config)
            if session_id or auto_save_name:
                apply_cli_session_continuity(agent, session_id or auto_save_name)
            result = agent.start(prompt)
            
            output.emit_result(
                message="Prompt completed",
                data={"result": str(result) if result else None}
            )
            
            # Don't print result again - actions mode already shows output
            return
        
        # Use handle_direct_prompt for other modes

        # Create args-like object for handle_direct_prompt
        class Args:
            pass
        
        args = Args()
        args.llm = model
        args.verbose = verbose
        args.memory = memory
        args.tools = tools
        args.toolset = toolset
        args.max_tokens = max_tokens
        args.web_search = False
        args.web_fetch = False
        args.prompt_caching = False
        args.planning = False
        args.planning_tools = None
        args.planning_reasoning = False
        args.auto_approve_plan = False
        args.final_agent = None
        args.user_id = None
        # Enable session features based on flags
        args.auto_save = auto_save_name
        args.history = None
        args.resume_session = session_id
        args.cli_project_sessions = bool(session_id or auto_save_name)
        args.include_rules = None if no_rules else "auto"
        args.no_rules = no_rules
        args.workflow = None
        args.workflow_var = None
        args.claude_memory = False
        args.guardrail = None
        args.metrics = False
        args.image = None
        args.image_generate = False
        args.telemetry = False
        args.mcp = None
        args.mcp_env = None
        args.fast_context = None
        args.handoff = None
        args.auto_memory = False
        args.todo = False
        args.router = False
        args.router_provider = None
        args.query_rewrite = False
        args.rewrite_tools = None
        args.expand_prompt = False
        args.expand_tools = None
        args.no_tools = False
        args.approval = approval
        
        praison.args = args
        
        result = praison.handle_direct_prompt(prompt)
        
        output.emit_result(
            message="Prompt completed",
            data={"result": str(result) if result else None}
        )
        
        if result and not output.is_json_mode:
            print(result)
    
    except Exception as e:
        output.emit_error(message=str(e))
        output.print_error(str(e))
        raise typer.Exit(1)


def _run_from_file_profiled(
    file_path: str,
    model: Optional[str] = None,
    framework: Optional[str] = None,
    verbose: bool = False,
    profile_deep: bool = False,
    continue_session: bool = False,
    session: Optional[str] = None,
    fork: bool = False,
    no_save: bool = False,
):
    """Run agents from a YAML file with profiling enabled."""
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
        from praisonai.cli.main import PraisonAI
    except ImportError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)
    profiler.mark_import_end()
    
    # Agent initialization phase
    profiler.mark_init_start()
    praison = PraisonAI(
        agent_file=file_path,
        framework=framework or "praisonai",
    )
    if model:
        praison.config_list[0]['model'] = model
    profiler.mark_init_end()
    
    # Execution phase
    profiler.mark_exec_start()
    result = praison.run()
    profiler.mark_exec_end()
    
    profiler.stop()
    
    # Print result
    if result:
        print(result)
    
    # Print profiling report
    profiler.print_report()


def _run_custom_agent(
    agent_config: Dict[str, Any],
    prompt: str,
    model: Optional[str] = None,
    verbose: bool = False,
    stream: bool = True,
    trace: bool = False,
    memory: bool = False,
    tools: Optional[str] = None,
    toolset: Optional[str] = None,
    max_tokens: int = 16000,
    output_mode: Optional[str] = None,
    continue_session: bool = False,
    session: Optional[str] = None,
    fork: bool = False,
    no_save: bool = False,
):
    """Run a custom agent definition."""
    output = get_output_controller()
    
    try:
        from praisonaiagents import Agent
        
        # Override model if specified
        if model:
            agent_config["llm"] = model
        
        # Add verbose flag
        if verbose:
            agent_config["verbose"] = verbose
        
        # Handle session continuity
        session_id = None
        auto_save_name = None
        
        if continue_session or session or fork:
            from ..state.project_sessions import get_project_session_store, find_last_session
            
            if continue_session:
                session_id = find_last_session()
                if session_id:
                    output.print_info(f"Continuing session: {session_id}")
                else:
                    output.print_warning("No previous sessions found. Starting new session.")
                    
            elif session:
                project_store = get_project_session_store()
                if project_store.session_exists(session):
                    session_id = session
                    output.print_info(f"Resuming session: {session_id}")
                else:
                    output.print_error(f"Session not found: {session}")
                    raise typer.Exit(1)
                
                if fork:
                    from praisonaiagents.session.hierarchy import HierarchicalSessionStore
                    from ..utils.project import get_project_sessions_dir
                    
                    hierarchical_store = HierarchicalSessionStore(str(get_project_sessions_dir()))
                    forked_session_id = hierarchical_store.fork_session(session_id)
                    session_id = forked_session_id
                    output.print_info(f"Forked session {session} -> {forked_session_id}")
        
        if not no_save:
            import uuid
            auto_save_name = session_id or "session-" + str(uuid.uuid4())[:8]
        
        # Add session support to agent config
        if session_id:
            agent_config["resume_session"] = session_id
        if auto_save_name:
            agent_config["auto_save"] = auto_save_name
        
        # Create and run agent
        agent = Agent(**agent_config)
        result = agent.start(prompt)
        
        output.emit_result(
            message="Agent completed",
            data={"result": str(result) if result else None}
        )
        
        if result and not output.is_json_mode:
            print(result)
    
    except Exception as e:
        output.emit_error(message=str(e))
        output.print_error(str(e))
        raise typer.Exit(1)


def _run_prompt_profiled(
    prompt: str,
    model: Optional[str] = None,
    verbose: bool = False,
    profile_deep: bool = False,
    continue_session: bool = False,
    session: Optional[str] = None,
    fork: bool = False,
    no_save: bool = False,
):
    """Run a direct prompt with profiling enabled."""
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
        "name": "RunAgent",
        "role": "Assistant",
        "goal": "Complete the task",
        "verbose": verbose,
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
