"""
PraisonAI CLI Typer Application.

Main Typer app that registers all command groups and handles global options.
"""

import importlib
from enum import Enum
from typing import Optional, Dict, Tuple, List

import typer
import click
from typer.core import TyperGroup
from typer.main import get_command as typer_get_command

from .output.console import OutputController, OutputMode, set_output_controller
from .state.identifiers import create_context


def _setup_langfuse_observability(*, verbose: bool = False) -> None:
    """Set up Langfuse observability by wiring TraceSink to action emitter."""
    try:
        from praisonai.observability.langfuse import LangfuseSink
        from praisonaiagents.trace.protocol import TraceEmitter, set_default_emitter
        from praisonaiagents.trace.context_events import ContextTraceEmitter, set_context_emitter
        import atexit
        
        # Create LangfuseSink (auto-reads env vars)
        sink = LangfuseSink()
        
        # Set up action-level trace emitter (covers RouterAgent / PlanningAgent)
        emitter = TraceEmitter(sink=sink, enabled=True)
        set_default_emitter(emitter)
        
        # Set up context-level trace emitter (captures Agent.start() lifecycle)
        context_emitter = ContextTraceEmitter(sink=sink.context_sink(), enabled=True)
        set_context_emitter(context_emitter)
        
        # Register atexit close for the sink
        atexit.register(sink.close)
        
    except ImportError:
        # Gracefully degrade if Langfuse not installed
        pass
    except Exception as e:
        # Avoid breaking CLI if observability setup fails
        if verbose:
            typer.echo(f"Warning: failed to initialize Langfuse observability: {e}", err=True)


def _setup_langextract_observability(*, verbose: bool = False) -> None:
    """Set up Langextract observability by wiring TraceSink to action emitter."""
    try:
        import importlib.util
        
        # Explicitly check if langextract is available before attempting to use it
        if importlib.util.find_spec('langextract') is None:
            if verbose:
                typer.echo("Warning: langextract is not installed. Install with: pip install 'praisonai[langextract]'", err=True)
            return
        
        from praisonai.observability.langextract import LangextractSink, LangextractSinkConfig
        from praisonaiagents.trace.protocol import TraceEmitter, set_default_emitter
        import os
        import atexit
        
        # Build LangextractSinkConfig from env vars
        config = LangextractSinkConfig(
            output_path=os.getenv("PRAISONAI_LANGEXTRACT_OUTPUT", "praisonai-trace.html"),
            auto_open=os.getenv("PRAISONAI_LANGEXTRACT_AUTO_OPEN", "false").lower() == "true",
        )
        
        # Create LangextractSink
        sink = LangextractSink(config=config)
        
        # Ensure sink is closed on exit to write the trace file
        atexit.register(sink.close)
        
        # Set up action-level trace emitter (covers RouterAgent / PlanningAgent)
        emitter = TraceEmitter(sink=sink, enabled=True)
        set_default_emitter(emitter)

        # Bridge the context emitter so regular Agent.start / tool calls / LLM
        # responses are captured as well.  Without this, typical single-agent
        # flows produce an empty trace (no agent_start/end, no tool events).
        def warn_handler(msg: str):
            if verbose:
                typer.echo(f"Warning: {msg}", err=True)
                
        LangextractSink.bridge_context_events(
            sink=sink,
            session_id="praisonai-cli",
            warn_callback=warn_handler
        )

    except ImportError:
        # Gracefully degrade if langextract not installed
        if verbose:
            typer.echo("Warning: langextract is not installed. Install with: pip install 'praisonai[langextract]'", err=True)
    except Exception as e:
        # Avoid breaking CLI if observability setup fails
        if verbose:
            typer.echo(f"Warning: failed to initialize langextract observability: {e}", err=True)


class OutputFormat(str, Enum):
    """Output format options."""
    text = "text"
    json = "json"
    stream_json = "stream-json"


# Command registry for lazy loading
_LAZY_COMMANDS: Dict[str, Tuple[str, str, str]] = {
    # Core commands
    "config": (".commands.config", "app", "Configuration management"),
    "traces": (".commands.traces", "app", "Trace collection management"),
    "env": (".commands.environment", "app", "Environment and diagnostics"),
    "auth": (".commands.auth", "app", "Credential management"),
    "session": (".commands.session", "app", "Session management"),
    "completion": (".commands.completion", "app", "Shell completion scripts"),
    "version": (".commands.version", "app", "Version information"),
    "debug": (".commands.debug", "app", "Debug and test interactive flows"),
    "lsp": (".commands.lsp", "app", "LSP service lifecycle"),
    "diag": (".commands.diag", "app", "Diagnostics export"),
    "doctor": (".commands.doctor", "app", "Health checks and diagnostics"),
    "setup": (".commands.setup", "app", "Interactive onboarding / configuration wizard"),
    "onboard": (".commands.onboard", "app", "Messaging bot onboarding wizard"),
    "obs": (".commands.obs", "app", "Observability diagnostics and management"),
    "acp": (".commands.acp", "app", "Agent Client Protocol server"),
    "mcp": (".commands.mcp", "app", "MCP server management"),
    "serve": (".commands.serve", "app", "API server management"),
    "schedule": (".commands.schedule", "app", "Scheduler management"),
    "kanban": (".commands.kanban", "app", "Kanban task management"),
    "run": (".commands.run", "app", "Run agents"),
    "profile": (".commands.profile", "app", "Performance profiling and diagnostics"),
    "benchmark": (".commands.benchmark", "app", "Comprehensive performance benchmarking"),
    "paths": (".commands.paths", "app", "Storage path inspection and migration"),
    
    # Terminal-native commands
    "chat": (".commands.chat", "app", "Terminal-native interactive chat (REPL)"),
    "code": (".commands.code", "app", "Terminal-native code assistant"),
    "call": (".commands.call", "app", "Voice/call interaction mode"),
    "realtime": (".commands.realtime", "app", "Realtime interaction mode"),
    "train": (".commands.train", "app", "Model training and fine-tuning"),
    "ui": (".commands.ui", "app", "🤖 Clean Chat UI (praisonaiui)"),
    "context": (".commands.context", "app", "Context management"),
    "research": (".commands.research", "app", "Research and analysis"),
    "memory": (".commands.memory", "app", "Memory management"),
    "workflow": (".commands.workflow", "app", "Workflow management"),
    "tools": (".commands.tools", "app", "Tool management"),
    "n8n": (".commands.n8n", "app", "n8n visual workflow editor integration"),
    "knowledge": (".commands.knowledge", "app", "Knowledge base management (legacy)"),
    "rag": (".commands.rag", "app", "RAG commands (legacy - use index/query instead)"),
    "deploy": (".commands.deploy", "app", "Deployment management"),
    "agents": (".commands.agents", "app", "Agent management"),
    "skills": (".commands.skills", "app", "Skill management"),
    "eval": (".commands.eval", "app", "Evaluation and testing"),
    "templates": (".commands.templates", "app", "Template management"),
    "recipe": (".commands.recipe", "app", "Recipe management"),
    "todo": (".commands.todo", "app", "Todo/task management"),
    "docs": (".commands.docs", "app", "Documentation management"),
    "commit": (".commands.commit", "app", "AI-assisted git commits"),
    "publish": (".commands.publish", "app", "Package publishing"),
    "hooks": (".commands.hooks", "app", "Hook management"),
    "rules": (".commands.rules", "app", "Rules management"),
    "registry": (".commands.registry", "app", "Registry management"),
    "package": (".commands.package", "app", "Package management"),
    "endpoints": (".commands.endpoints", "app", "API endpoint management"),
    "test": (".commands.test", "app", "Run test suite with tier and provider options"),
    "examples": (".commands.examples", "app", "Run and manage example files"),
    "batch": (".commands.batch", "app", "Run all PraisonAI scripts in current folder"),
    "replay": (".commands.replay", "app", "Context replay for debugging agent execution"),
    "loop": (".commands.loop", "app", "Autonomous agent execution loops"),
    "tracker": (".commands.tracker", "app", "Autonomous agent tracking with step-by-step analysis"),
    "github": (".commands.github", "app", "GitHub native context tracking and Issue triage"),
    "managed": (".commands.managed", "app", "Managed Agents (Anthropic cloud-hosted backend)"),
    
    # Moltbot-inspired commands
    "bot": (".commands.bot", "app", "Messaging bots with full agent capabilities"),
    "gateway": (".commands.gateway", "app", "Multi-bot WebSocket gateway server"),
    "pairing": (".commands.pairing", "app", "Manage bot user pairing"),
    "browser": (".commands.browser", "app", "Browser control for agent automation"),
    "plugins": (".commands.plugins", "app", "Plugin management and inspection"),
    "sandbox": (".commands.sandbox", "app", "Sandbox container management"),
    "claw": (".commands.claw", "app", "🦞 PraisonAI Dashboard (full UI)"),
    "flow": (".commands.flow", "app", "Visual workflow builder (Langflow)"),
    "dashboard": (".commands.dashboard", "app", "🌟 Unified Dashboard (Flow + Claw + UI)"),
    "langfuse": (".commands.langfuse", "app", "🔍 Langfuse observability platform"),
    "langextract": (".commands.langextract", "app", "🧠 Langextract visual trace layer"),
    "port": (".commands.port", "app", "🔌 Manage port usage and resolve conflicts"),
    "up": (".commands.up", "app", "🚀 Start unified PraisonAI stack (Langfuse + Langflow)"),
}

# Special commands that need custom handling
_SPECIAL_COMMANDS = {
    "tui": (".features.tui.debug", "create_debug_app", "Interactive TUI and simulation"),
    "queue": (".features.tui.cli", "create_queue_app", "Queue management"),
}


class LazyCommandGroup(TyperGroup):
    """Click Group that lazily loads subcommands from registry."""
    
    def list_commands(self, ctx: click.Context) -> List[str]:
        """Return list of available commands without importing them."""
        # Start with commands from parent (already registered commands)
        commands = set(super().list_commands(ctx))
        
        # Add lazy-loaded commands
        commands.update(_LAZY_COMMANDS.keys())
        commands.update(_SPECIAL_COMMANDS.keys())
        
        # Add special inline commands
        commands.add("app")
        
        # Add retrieval commands (these are registered via register_commands)
        commands.update(["index", "query", "search"])
        
        # Add standardise/standardize
        commands.update(["standardise", "standardize"])
        
        return sorted(list(commands))
    
    def get_command(self, ctx: click.Context, name: str) -> Optional[click.Command]:
        """Lazily import and return the command."""
        # First check if command is already registered (e.g., retrieval commands)
        existing = super().get_command(ctx, name)
        if existing is not None:
            return existing
        
        # Check regular lazy commands
        if name in _LAZY_COMMANDS:
            module_path, attr_name, _ = _LAZY_COMMANDS[name]
            try:
                module = importlib.import_module(module_path, __package__)
                sub_app = getattr(module, attr_name)
                return typer_get_command(sub_app)
            except (ImportError, AttributeError) as e:
                typer.echo(f"Error loading command '{name}': {e}", err=True)
                return None
        
        # Check special commands
        if name in _SPECIAL_COMMANDS:
            module_path, func_name, _ = _SPECIAL_COMMANDS[name]
            try:
                module = importlib.import_module(module_path, __package__)
                create_func = getattr(module, func_name)
                sub_app = create_func()
                if sub_app:
                    return typer_get_command(sub_app)
            except (ImportError, AttributeError) as e:
                typer.echo(f"Error loading command '{name}': {e}", err=True)
                return None
        
        # Handle standardise/standardize
        if name in ["standardise", "standardize"]:
            return self._get_standardise_command()
        
        # Handle app command
        if name == "app":
            return self._get_app_command()
        
        return None
    
    def _get_standardise_command(self) -> Optional[click.Command]:
        """Get the standardise command group."""
        try:
            standardise_app = typer.Typer()
            
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
            
            return typer_get_command(standardise_app)
        except Exception:
            return None
    
    def _get_app_command(self) -> Optional[click.Command]:
        """Get the app command."""
        # Create a local Typer app to avoid mutating the global app
        app_group = typer.Typer(add_completion=False)
        
        @app_group.command(name="app", context_settings={"allow_interspersed_args": False})
        def app_cmd(
            port: int = typer.Option(8000, "--port", "-p", help="Port to listen on"),
            host: str = typer.Option("0.0.0.0", "--host", "-h", help="Host to bind to"),
            config: str = typer.Option(None, "--config", "-c", help="Path to config file (YAML)"),
            reload: bool = typer.Option(False, "--reload", "-r", help="Enable auto-reload for development"),
            debug: bool = typer.Option(False, "--debug", "-d", help="Enable debug mode"),
            name: str = typer.Option("PraisonAI App", "--name", "-n", help="Application name"),
        ):
            """
            Start an AgentOS server for production deployment.
            
            AgentOS provides a FastAPI-based web service for deploying AI agents
            with REST and WebSocket endpoints.
            """
            from rich.console import Console
            console = Console()
            
            try:
                from praisonai import AgentOS
                from praisonaiagents import AgentOSConfig
            except ImportError as e:
                console.print(f"[red]Error importing AgentOS: {e}[/red]")
                console.print("[yellow]Install with: pip install praisonai[api][/yellow]")
                raise typer.Abort()
            
            # Load agents from config file if provided
            agents = []
            if config:
                agents = self._load_agents_from_config_file(config, console)
            
            # Create config
            app_config = AgentOSConfig(
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
                agent_app = AgentOS(
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
        
        # Bind the helper method to the function for later use
        app_cmd._load_agents_from_config_file = self._load_agents_from_config_file
        
        # Return the click.Command object (not the raw function)
        return typer_get_command(app_group)
    
    def _load_agents_from_config_file(self, config_path: str, console) -> list:
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


# Create main Typer app with lazy loading group
app = typer.Typer(
    name="praisonai",
    help="PraisonAI - AI Agents Framework CLI",
    add_completion=False,  # We handle completion manually
    no_args_is_help=False,  # Allow running without args for legacy compatibility
    rich_markup_mode="rich",
    cls=LazyCommandGroup,  # Use our lazy loading command group
)


# Global state for options
class GlobalState:
    """Global state for CLI options."""
    output_format: OutputFormat = OutputFormat.text
    no_color: bool = False
    quiet: bool = False
    verbose: bool = False
    screen_reader: bool = False
    observe: Optional[str] = None
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
    observe: Optional[str] = typer.Option(
        None,
        "--observe",
        "-O",
        help="Enable observability (langfuse, langextract)",
        envvar="PRAISONAI_OBSERVE",
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
    state.observe = observe
    
    # Handle --json alias
    if json_output:
        state.output_format = OutputFormat.json
    
    # Validate and set up observability if requested
    if observe:
        if observe == "langfuse":
            _setup_langfuse_observability(verbose=verbose)
        elif observe == "langextract":
            _setup_langextract_observability(verbose=verbose)
        else:
            raise typer.BadParameter(
                f"Unsupported observe provider: {observe}. "
                "Choose one of: langfuse, langextract."
            )
    
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
    
    # Install warning filters for CLI usage only
    from .main import install_warning_filters
    install_warning_filters()
    
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
_commands_registered = False

def register_commands():
    """Register all command groups (idempotent).

    With lazy loading, this function now only registers the retrieval commands
    that need special handling. All other commands are loaded on-demand through
    the LazyCommandGroup.
    """
    global _commands_registered
    if _commands_registered:
        return
    
    # Register retrieval commands (these need special handling)
    try:
        from .commands import retrieval as retrieval_module
        retrieval_module.register_commands(app)
    except ImportError:
        pass  # Graceful degradation
    
    # Mark registration complete
    _commands_registered = True


# Register commands on import
register_commands()