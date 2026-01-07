"""
PraisonAI CLI Typer Application.

Main Typer app that registers all command groups and handles global options.
"""

import os
import sys
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
    
    # If no command provided, show help or handle legacy behavior
    if ctx.invoked_subcommand is None:
        # Check if there are remaining args (legacy behavior)
        # This is handled by the legacy adapter in main.py
        pass


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
    
    # Register sub-apps - Previously legacy-only commands (now visible in --help)
    app.add_typer(chat_app, name="chat", help="Interactive chat mode")
    app.add_typer(code_app, name="code", help="Code assistant mode")
    app.add_typer(call_app, name="call", help="Voice/call interaction mode")
    app.add_typer(realtime_app, name="realtime", help="Realtime interaction mode")
    app.add_typer(train_app, name="train", help="Model training and fine-tuning")
    app.add_typer(ui_app, name="ui", help="Web UI management")
    app.add_typer(context_app, name="context", help="Context management")
    app.add_typer(research_app, name="research", help="Research and analysis")
    app.add_typer(memory_app, name="memory", help="Memory management")
    app.add_typer(workflow_app, name="workflow", help="Workflow management")
    app.add_typer(tools_app, name="tools", help="Tool management")
    app.add_typer(knowledge_app, name="knowledge", help="Knowledge base management")
    app.add_typer(rag_app, name="rag", help="RAG (Retrieval Augmented Generation)")
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
    
    # Register TUI and queue commands
    tui_app = create_tui_debug_app()
    queue_app = create_queue_app()
    if tui_app:
        app.add_typer(tui_app, name="tui", help="Interactive TUI and simulation")
    if queue_app:
        app.add_typer(queue_app, name="queue", help="Queue management")


# Register commands on import
register_commands()
