"""
Run command group for PraisonAI CLI.

Provides agent execution commands.
"""

from typing import Optional

import typer

from ..output.console import get_output_controller
from ..state.identifiers import get_current_context

app = typer.Typer(help="Run agents")


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
    max_tokens: int = typer.Option(16000, "--max-tokens", help="Maximum output tokens"),
    profile: bool = typer.Option(False, "--profile", help="Enable CLI profiling (timing breakdown)"),
    profile_deep: bool = typer.Option(False, "--profile-deep", help="Enable deep profiling (cProfile stats, higher overhead)"),
    output_mode: Optional[str] = typer.Option(None, "--output", "-o", help="Output mode: silent (default), actions, verbose, json, stream"),
):
    """
    Run agents from a file or prompt.
    
    Examples:
        praisonai run agents.yaml
        praisonai run "What is the weather?"
        praisonai run agents.yaml --interactive
        praisonai run "What is 2+2?" --profile
    """
    output = get_output_controller()
    _ = get_current_context()  # Initialize context
    
    if not target:
        output.print_panel(
            "Run agents from a file or prompt.\n\n"
            "Usage:\n"
            "  praisonai run agents.yaml\n"
            "  praisonai run \"What is the weather?\"\n"
            "  praisonai run agents.yaml --interactive\n\n"
            "Options:\n"
            "  --model, -m       LLM model to use\n"
            "  --framework, -f   Framework (praisonai, crewai, autogen)\n"
            "  --interactive, -i Interactive mode\n"
            "  --verbose, -v     Verbose output\n"
            "  --trace           Enable tracing\n"
            "  --memory          Enable memory",
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
            )
        else:
            # Profiling for direct prompt
            _run_prompt_profiled(
                target,
                model=model,
                verbose=verbose,
                profile_deep=profile_deep,
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
            max_tokens=max_tokens,
            output_mode=output_mode,
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
):
    """Run agents from a YAML file."""
    output = get_output_controller()
    
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
    max_tokens: int = 16000,
    output_mode: Optional[str] = None,
):
    """Run a direct prompt."""
    output = get_output_controller()
    
    try:
        # If output_mode is "actions", use direct Agent with actions preset
        if output_mode == "actions":
            from praisonaiagents import Agent
            
            agent_config = {
                "name": "RunAgent",
                "role": "Assistant", 
                "goal": "Complete the task",
                "output": "actions",  # Use actions preset
            }
            if model:
                agent_config["llm"] = model
            
            agent = Agent(**agent_config)
            result = agent.start(prompt)
            
            output.emit_result(
                message="Prompt completed",
                data={"result": str(result) if result else None}
            )
            
            # Don't print result again - actions mode already shows output
            return
        
        # Use existing handle_direct_prompt for other modes
        from praisonai.cli.main import PraisonAI
        
        praison = PraisonAI()
        
        if model:
            praison.config_list[0]['model'] = model
        
        # Create args-like object for handle_direct_prompt
        class Args:
            pass
        
        args = Args()
        args.llm = model
        args.verbose = verbose
        args.memory = memory
        args.tools = tools
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
        args.auto_save = None
        args.history = None
        args.include_rules = None
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


def _run_prompt_profiled(
    prompt: str,
    model: Optional[str] = None,
    verbose: bool = False,
    profile_deep: bool = False,
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
