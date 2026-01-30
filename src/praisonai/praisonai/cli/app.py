"""
PraisonAI CLI Typer Application.

Main Typer app that registers all command groups and handles global options.
"""

from enum import Enum
from typing import Optional

import typer

from .output.console import OutputController, OutputMode, set_output_controller
from .state.identifiers import create_context


class OutputFormat(str, Enum):
    """Output format options."""
    text = "text"
    json = "json"
    stream_json = "stream-json"


# Create main Typer app
app = typer.Typer(
    name="praisonai",
    help="PraisonAI - AI Agents Framework CLI",
    add_completion=False,  # We handle completion manually
    no_args_is_help=False,  # Allow running without args for legacy compatibility
    rich_markup_mode="rich",
)


# Global state for options
class GlobalState:
    """Global state for CLI options."""
    output_format: OutputFormat = OutputFormat.text
    no_color: bool = False
    quiet: bool = False
    verbose: bool = False
    screen_reader: bool = False
    output_controller: Optional[OutputController] = None


state = GlobalState()


def version_callback(value: bool):
    """Show version and exit."""
    if value:
        from praisonai.version import __version__
        typer.echo(f"PraisonAI version {__version__}")
        raise typer.Exit()


@app.callback(invoke_without_command=True)
def main_callback(
    ctx: typer.Context,
    version: bool = typer.Option(
        False,
        "--version",
        "-V",
        callback=version_callback,
        is_eager=True,
        help="Show version and exit",
    ),
    output_format: OutputFormat = typer.Option(
        OutputFormat.text,
        "--output-format",
        "-o",
        help="Output format",
        envvar="PRAISONAI_OUTPUT_FORMAT",
    ),
    json_output: bool = typer.Option(
        False,
        "--json",
        help="Output in JSON format (alias for --output-format json)",
    ),
    no_color: bool = typer.Option(
        False,
        "--no-color",
        help="Disable colored output",
        envvar="NO_COLOR",
    ),
    quiet: bool = typer.Option(
        False,
        "--quiet",
        "-q",
        help="Minimal output",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Verbose output with debug details",
    ),
    screen_reader: bool = typer.Option(
        False,
        "--screen-reader",
        help="Screen reader friendly output (no spinners/panels)",
    ),
):
    """
    PraisonAI - AI Agents Framework CLI.
    
    Run agents, manage configuration, and more.
    """
    # Store global options
    state.output_format = output_format
    state.no_color = no_color
    state.quiet = quiet
    state.verbose = verbose
    state.screen_reader = screen_reader
    
    # Handle --json alias
    if json_output:
        state.output_format = OutputFormat.json
    
    # Determine output mode
    if state.quiet:
        mode = OutputMode.QUIET
    elif state.verbose:
        mode = OutputMode.VERBOSE
    elif state.screen_reader:
        mode = OutputMode.SCREEN_READER
    elif state.output_format == OutputFormat.json:
        mode = OutputMode.JSON
    elif state.output_format == OutputFormat.stream_json:
        mode = OutputMode.STREAM_JSON
    else:
        mode = OutputMode.TEXT
    
    # Create run context
    context = create_context()
    
    # Create and set output controller
    state.output_controller = OutputController(
        mode=mode,
        no_color=state.no_color,
        run_id=context.run_id,
        trace_id=context.trace_id,
    )
    set_output_controller(state.output_controller)
    
    # If no command provided, start interactive mode
    if ctx.invoked_subcommand is None:
        from praisonai.cli.interactive.async_tui import AsyncTUI, AsyncTUIConfig
        
        tui_config = AsyncTUIConfig(
            model="gpt-4o-mini",
            show_logo=True,
            show_status_bar=state.output_format != OutputFormat.json,
        )
        
        tui = AsyncTUI(config=tui_config)
        tui.run()


def get_output_controller() -> OutputController:
    """Get the current output controller."""
    if state.output_controller is None:
        state.output_controller = OutputController()
    return state.output_controller


# Import and register command groups
def register_commands():
    """Register all command groups."""
    # Import command modules - Core commands
    from .commands.config import app as config_app
    from .commands.traces import app as traces_app
    from .commands.environment import app as env_app
    from .commands.session import app as session_app
    from .commands.completion import app as completion_app
    from .commands.version import app as version_app
    from .commands.debug import app as debug_app
    from .commands.lsp import app as lsp_app
    from .commands.diag import app as diag_app
    from .commands.doctor import app as doctor_app
    from .commands.acp import app as acp_app
    from .commands.mcp import app as mcp_app
    from .commands.serve import app as serve_app
    from .commands.schedule import app as schedule_app
    from .commands.run import app as run_app
    from .commands.profile import app as profile_app
    from .commands.benchmark import app as benchmark_app
    
    # Import new command modules - Previously legacy-only commands
    from .commands.chat import app as chat_app
    from .commands.code import app as code_app
    from .commands.call import app as call_app
    from .commands.realtime import app as realtime_app
    from .commands.train import app as train_app
    from .commands.ui import app as ui_app
    from .commands.context import app as context_app
    from .commands.research import app as research_app
    from .commands.memory import app as memory_app
    from .commands.workflow import app as workflow_app
    from .commands.tools import app as tools_app
    from .commands.knowledge import app as knowledge_app
    from .commands.rag import app as rag_app
    from .commands import retrieval as retrieval_module
    from .commands.deploy import app as deploy_app
    from .commands.agents import app as agents_app
    from .commands.skills import app as skills_app
    from .commands.eval import app as eval_app
    from .commands.templates import app as templates_app
    from .commands.recipe import app as recipe_app
    from .commands.todo import app as todo_app
    from .commands.docs import app as docs_app
    from .commands.commit import app as commit_app
    from .commands.hooks import app as hooks_app
    from .commands.rules import app as rules_app
    from .commands.registry import app as registry_app
    from .commands.package import app as package_app
    from .commands.endpoints import app as endpoints_app
    from .commands.test import app as test_app
    from .commands.examples import app as examples_app
    from .commands.batch import app as batch_app
    from .commands.replay import app as replay_app
    from .commands.loop import app as loop_app
    
    # Import new moltbot-inspired commands
    from .commands.bot import app as bot_app
    from .commands.browser import app as browser_app
    from .commands.plugins import app as plugins_app
    from .commands.sandbox import app as sandbox_app
    
    # Import TUI and queue commands
    from .features.tui.debug import create_debug_app as create_tui_debug_app
    from .features.tui.cli import create_queue_app
    
    # Register sub-apps - Core commands
    app.add_typer(config_app, name="config", help="Configuration management")
    app.add_typer(traces_app, name="traces", help="Trace collection management")
    app.add_typer(env_app, name="env", help="Environment and diagnostics")
    app.add_typer(session_app, name="session", help="Session management")
    app.add_typer(completion_app, name="completion", help="Shell completion scripts")
    app.add_typer(version_app, name="version", help="Version information")
    app.add_typer(debug_app, name="debug", help="Debug and test interactive flows")
    app.add_typer(lsp_app, name="lsp", help="LSP service lifecycle")
    app.add_typer(diag_app, name="diag", help="Diagnostics export")
    app.add_typer(doctor_app, name="doctor", help="Health checks and diagnostics")
    app.add_typer(acp_app, name="acp", help="Agent Client Protocol server")
    app.add_typer(mcp_app, name="mcp", help="MCP server management")
    app.add_typer(serve_app, name="serve", help="API server management")
    app.add_typer(schedule_app, name="schedule", help="Scheduler management")
    app.add_typer(run_app, name="run", help="Run agents")
    app.add_typer(profile_app, name="profile", help="Performance profiling and diagnostics")
    app.add_typer(benchmark_app, name="benchmark", help="Comprehensive performance benchmarking")
    
    # Register sub-apps - Terminal-native commands
    app.add_typer(chat_app, name="chat", help="Terminal-native interactive chat (REPL)")
    app.add_typer(code_app, name="code", help="Terminal-native code assistant")
    app.add_typer(call_app, name="call", help="Voice/call interaction mode")
    app.add_typer(realtime_app, name="realtime", help="Realtime interaction mode")
    app.add_typer(train_app, name="train", help="Model training and fine-tuning")
    app.add_typer(ui_app, name="ui", help="Web UI management")
    app.add_typer(context_app, name="context", help="Context management")
    app.add_typer(research_app, name="research", help="Research and analysis")
    app.add_typer(memory_app, name="memory", help="Memory management")
    app.add_typer(workflow_app, name="workflow", help="Workflow management")
    app.add_typer(tools_app, name="tools", help="Tool management")
    app.add_typer(knowledge_app, name="knowledge", help="Knowledge base management (legacy)")
    app.add_typer(rag_app, name="rag", help="RAG commands (legacy - use index/query instead)")
    
    # Register unified retrieval commands (Agent-first)
    retrieval_module.register_commands(app)
    app.add_typer(deploy_app, name="deploy", help="Deployment management")
    app.add_typer(agents_app, name="agents", help="Agent management")
    app.add_typer(skills_app, name="skills", help="Skill management")
    app.add_typer(eval_app, name="eval", help="Evaluation and testing")
    app.add_typer(templates_app, name="templates", help="Template management")
    app.add_typer(recipe_app, name="recipe", help="Recipe management")
    app.add_typer(todo_app, name="todo", help="Todo/task management")
    app.add_typer(docs_app, name="docs", help="Documentation management")
    app.add_typer(commit_app, name="commit", help="AI-assisted git commits")
    app.add_typer(hooks_app, name="hooks", help="Hook management")
    app.add_typer(rules_app, name="rules", help="Rules management")
    app.add_typer(registry_app, name="registry", help="Registry management")
    app.add_typer(package_app, name="package", help="Package management")
    app.add_typer(endpoints_app, name="endpoints", help="API endpoint management")
    app.add_typer(test_app, name="test", help="Run test suite with tier and provider options")
    app.add_typer(examples_app, name="examples", help="Run and manage example files")
    app.add_typer(batch_app, name="batch", help="Run all PraisonAI scripts in current folder")
    app.add_typer(replay_app, name="replay", help="Context replay for debugging agent execution")
    app.add_typer(loop_app, name="loop", help="Autonomous agent execution loops")
    
    # Helper function for loading agents from config
    def _load_agents_from_config_file(config_path: str, console) -> list:
        """Load agents from a YAML config file."""
        import yaml
        
        try:
            with open(config_path, 'r') as f:
                config_data = yaml.safe_load(f)
        except Exception as e:
            console.print(f"[red]Error loading config: {e}[/red]")
            return []
        
        if not config_data:
            return []
        
        agents = []
        
        # Try to load agents from config
        agents_config = config_data.get('agents', [])
        if not agents_config and 'agent' in config_data:
            agents_config = [config_data['agent']]
        
        if agents_config:
            try:
                from praisonaiagents import Agent
                
                for agent_data in agents_config:
                    if isinstance(agent_data, dict):
                        agent = Agent(
                            name=agent_data.get('name', 'Agent'),
                            role=agent_data.get('role'),
                            instructions=agent_data.get('instructions', agent_data.get('goal', '')),
                            llm=agent_data.get('llm'),
                        )
                        agents.append(agent)
                        console.print(f"[green]✓ Loaded agent: {agent.name}[/green]")
            except Exception as e:
                console.print(f"[yellow]Warning: Could not load agents from config: {e}[/yellow]")
        
        return agents
    
    # Register app command directly using Typer
    @app.command(name="app")
    def app_cmd(
        port: int = typer.Option(8000, "--port", "-p", help="Port to listen on"),
        host: str = typer.Option("0.0.0.0", "--host", "-h", help="Host to bind to"),
        config: str = typer.Option(None, "--config", "-c", help="Path to config file (YAML)"),
        reload: bool = typer.Option(False, "--reload", "-r", help="Enable auto-reload for development"),
        debug: bool = typer.Option(False, "--debug", "-d", help="Enable debug mode"),
        name: str = typer.Option("PraisonAI App", "--name", "-n", help="Application name"),
    ):
        """
        Start an AgentApp server for production deployment.
        
        AgentApp provides a FastAPI-based web service for deploying AI agents
        with REST and WebSocket endpoints.
        """
        from rich.console import Console
        console = Console()
        
        try:
            from praisonai import AgentApp
            from praisonaiagents import AgentAppConfig
        except ImportError as e:
            console.print(f"[red]Error importing AgentApp: {e}[/red]")
            console.print("[yellow]Install with: pip install praisonai[api][/yellow]")
            raise typer.Abort()
        
        # Load agents from config file if provided
        agents = []
        if config:
            agents = _load_agents_from_config_file(config, console)
        
        # Create config
        app_config = AgentAppConfig(
            name=name,
            host=host,
            port=port,
            reload=reload,
            debug=debug,
        )
        
        # Create and start app
        console.print(f"\n[bold green]🚀 Starting {name}[/bold green]")
        console.print(f"[dim]Host: {host}:{port}[/dim]")
        if agents:
            console.print(f"[dim]Agents: {len(agents)}[/dim]")
        if reload:
            console.print("[yellow]Auto-reload enabled (development mode)[/yellow]")
        console.print()
        
        try:
            agent_app = AgentApp(
                name=name,
                agents=agents,
                config=app_config,
            )
            agent_app.serve()
        except ImportError as e:
            console.print(f"[red]Missing dependency: {e}[/red]")
            console.print("[yellow]Install with: pip install praisonai[api][/yellow]")
            raise typer.Abort()
        except Exception as e:
            console.print(f"[red]Error starting server: {e}[/red]")
            raise typer.Abort()
    
    # Register moltbot-inspired commands
    app.add_typer(bot_app, name="bot", help="Messaging bots with full agent capabilities")
    app.add_typer(browser_app, name="browser", help="Browser control for agent automation")
    app.add_typer(plugins_app, name="plugins", help="Plugin management and inspection")
    app.add_typer(sandbox_app, name="sandbox", help="Sandbox container management")
    
    # Register standardise command
    try:
        standardise_app = typer.Typer(name="standardise", help="Documentation and examples standardisation (FDEP)")
        
        @standardise_app.command("check")
        def standardise_check(
            path: str = typer.Option(".", "--path", "-p", help="Project root path"),
            feature: str = typer.Option(None, "--feature", help="Specific feature slug"),
            scope: str = typer.Option("all", "--scope", help="Scope: all, docs, examples, sdk, cli"),
            ci: bool = typer.Option(False, "--ci", help="CI mode"),
        ):
            """Check for standardisation issues."""
            from .commands.standardise import _run_check
            import argparse
            args = argparse.Namespace(path=path, feature=feature, scope=scope, ci=ci, dry_run=True)
            _run_check(args)
        
        @standardise_app.command("report")
        def standardise_report(
            path: str = typer.Option(".", "--path", "-p", help="Project root path"),
            format: str = typer.Option("text", "--format", "-f", help="Format: text, json, markdown"),
            output: str = typer.Option(None, "--output", "-o", help="Output file"),
            ci: bool = typer.Option(False, "--ci", help="CI mode"),
        ):
            """Generate detailed report."""
            from .commands.standardise import _run_report
            import argparse
            args = argparse.Namespace(path=path, format=format, output=output, ci=ci, feature=None, scope="all", dry_run=True)
            _run_report(args)
        
        @standardise_app.command("fix")
        def standardise_fix(
            path: str = typer.Option(".", "--path", "-p", help="Project root path"),
            feature: str = typer.Option(None, "--feature", help="Specific feature slug"),
            apply: bool = typer.Option(False, "--apply", help="Actually apply changes"),
            no_backup: bool = typer.Option(False, "--no-backup", help="Don't create backups"),
        ):
            """Fix standardisation issues."""
            from .commands.standardise import _run_fix
            import argparse
            args = argparse.Namespace(path=path, feature=feature, apply=apply, no_backup=no_backup, scope="all", ci=False, dry_run=not apply)
            _run_fix(args)
        
        @standardise_app.command("init")
        def standardise_init(
            feature: str = typer.Argument(..., help="Feature slug to initialise"),
            path: str = typer.Option(".", "--path", "-p", help="Project root path"),
            apply: bool = typer.Option(False, "--apply", help="Actually create files"),
        ):
            """Initialise a new feature with all required artifacts."""
            from .commands.standardise import _run_init
            import argparse
            args = argparse.Namespace(feature=feature, path=path, apply=apply, scope="all", ci=False, dry_run=not apply)
            _run_init(args)
        
        @standardise_app.command("ai")
        def standardise_ai(
            feature: str = typer.Argument(..., help="Feature slug to generate content for"),
            gen_type: str = typer.Option("all", "--type", "-t", help="Type: docs, examples, all"),
            apply: bool = typer.Option(False, "--apply", help="Actually create files"),
            verify: bool = typer.Option(False, "--verify", help="Verify with AI"),
            model: str = typer.Option("gpt-4o-mini", "--model", help="LLM model"),
            path: str = typer.Option(".", "--path", "-p", help="Project root path"),
        ):
            """AI-powered generation of docs/examples."""
            from .commands.standardise import _run_ai
            import argparse
            args = argparse.Namespace(feature=feature, type=gen_type, apply=apply, verify=verify, model=model, path=path, scope="all", ci=False, dry_run=not apply)
            _run_ai(args)
        
        @standardise_app.command("checkpoint")
        def standardise_checkpoint(
            message: str = typer.Option(None, "--message", "-m", help="Checkpoint message"),
            path: str = typer.Option(".", "--path", "-p", help="Repository path"),
        ):
            """Create an undo checkpoint."""
            from .commands.standardise import _run_checkpoint
            import argparse
            args = argparse.Namespace(message=message, path=path)
            _run_checkpoint(args)
        
        @standardise_app.command("undo")
        def standardise_undo(
            checkpoint: str = typer.Option(None, "--checkpoint", help="Checkpoint ID"),
            list_checkpoints: bool = typer.Option(False, "--list", help="List checkpoints"),
            path: str = typer.Option(".", "--path", "-p", help="Repository path"),
        ):
            """Undo to a previous checkpoint."""
            from .commands.standardise import _run_undo
            import argparse
            args = argparse.Namespace(checkpoint=checkpoint, list=list_checkpoints, path=path)
            _run_undo(args)
        
        @standardise_app.command("redo")
        def standardise_redo(
            path: str = typer.Option(".", "--path", "-p", help="Repository path"),
        ):
            """Redo after an undo."""
            from .commands.standardise import _run_redo
            import argparse
            args = argparse.Namespace(path=path)
            _run_redo(args)
        
        app.add_typer(standardise_app, name="standardise", help="Documentation and examples standardisation (FDEP)")
        # Also register as 'standardize' for US spelling
        app.add_typer(standardise_app, name="standardize", help="Documentation and examples standardisation (FDEP)")
    except Exception:
        pass  # Graceful degradation if standardise module not available
    
    # Register TUI and queue commands
    tui_app = create_tui_debug_app()
    queue_app = create_queue_app()
    if tui_app:
        app.add_typer(tui_app, name="tui", help="Interactive TUI and simulation")
    if queue_app:
        app.add_typer(queue_app, name="queue", help="Queue management")


# Register commands on import
register_commands()
