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
    stream: bool = typer.Option(True, "--stream/--no-stream", help="Stream output"),
    trace: bool = typer.Option(False, "--trace", help="Enable tracing"),
    memory: bool = typer.Option(False, "--memory", help="Enable memory"),
    tools: Optional[str] = typer.Option(None, "--tools", "-t", help="Tools file path"),
    max_tokens: int = typer.Option(16000, "--max-tokens", help="Maximum output tokens"),
):
    """
    Run agents from a file or prompt.
    
    Examples:
        praisonai run agents.yaml
        praisonai run "What is the weather?"
        praisonai run agents.yaml --interactive
    """
    output = get_output_controller()
    context = get_current_context()
    
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
):
    """Run a direct prompt."""
    output = get_output_controller()
    
    try:
        # Use existing handle_direct_prompt
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
