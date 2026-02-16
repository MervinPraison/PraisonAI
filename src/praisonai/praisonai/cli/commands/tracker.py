"""
Tracker command for autonomous agent execution with step-by-step tracking.

Uses the centralized autonomy system with:
- All default autonomy tools (search, file, shell, code, etc.)
- Auto-approval enabled by default (full_auto mode)
- Real-time step tracking and status output
- Summary table at completion
- Gap analysis for debugging

The tracker integrates with the Agent's autonomy system to provide
comprehensive tracking of autonomous agent execution.
"""

from typing import Optional, List
from dataclasses import dataclass, field
from datetime import datetime
import os
import time

import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

console = Console()

app = typer.Typer(
    name="tracker",
    help="Run agents in autonomous mode with step-by-step tracking",
    no_args_is_help=False,
)


@dataclass
class TrackedStep:
    """A single tracked step in the autonomous execution."""
    step_number: int
    timestamp: str
    action_type: str  # chat, tool_call, completion, error
    action_name: str  # tool name or "thinking"
    input_summary: str
    output_summary: str
    duration_seconds: float
    success: bool
    error: Optional[str] = None


@dataclass
class TrackerResult:
    """Result of a tracked autonomous execution."""
    task: str
    success: bool
    completion_reason: str
    total_steps: int
    total_duration: float
    steps: List[TrackedStep] = field(default_factory=list)
    tools_used: List[str] = field(default_factory=list)
    gaps_identified: List[str] = field(default_factory=list)


# ============================================================================
# CENTRALIZED AUTONOMY DEFAULT TOOLS
# These are the default tools available in autonomy mode (no API keys required)
# ============================================================================
AUTONOMY_DEFAULT_TOOLS = [
    # Web Search & Crawl
    "search_web",       # Unified web search (DuckDuckGo fallback)
    "internet_search",  # DuckDuckGo search
    "web_crawl",        # Web page crawling
    "scrape_page",      # Page scraping
    "extract_text",     # Text extraction
    "extract_links",    # Link extraction
    
    # File Operations
    "read_file",        # Read file contents
    "write_file",       # Write to files
    "list_files",       # List directory contents
    "copy_file",        # Copy files
    "move_file",        # Move files
    "delete_file",      # Delete files
    "get_file_info",    # Get file metadata
    
    # Shell & System
    "execute_command",  # Execute shell commands
    "list_processes",   # List running processes
    "get_system_info",  # Get system information
    
    # Python Code Execution
    "execute_code",     # Execute Python code
    "analyze_code",     # Analyze code structure
    "format_code",      # Format Python code
    "lint_code",        # Lint Python code
    
    # Scheduling
    "schedule_add",     # Add scheduled task
    "schedule_list",    # List scheduled tasks
    "schedule_remove",  # Remove scheduled task
]

# Extended tools (may require API keys)
EXTENDED_TOOLS = [
    "tavily_search",    # Tavily search (requires TAVILY_API_KEY)
    "tavily_extract",   # Tavily extract
    "exa_search",       # Exa search (requires EXA_API_KEY)
    "exa_answer",       # Exa answer
    "crawl4ai",         # Advanced crawling (requires playwright)
    "ydc_search",       # You.com search (requires YDC_API_KEY)
]


def _get_tools(tool_names: List[str]) -> List:
    """Resolve tool names to actual tool functions."""
    tools = []
    try:
        from praisonaiagents import tools as tool_module
        for name in tool_names:
            try:
                tool_func = getattr(tool_module, name)
                # Check if it's a module (e.g., web_crawl returns module)
                # In that case, get the function with the same name from the module
                if hasattr(tool_func, '__file__') and hasattr(tool_func, name):
                    tool_func = getattr(tool_func, name)
                tools.append(tool_func)
            except AttributeError:
                pass  # Silently skip unavailable tools
    except ImportError:
        console.print("[red]Error: praisonaiagents not installed[/red]")
    return tools


def _summarize_text(text: str, max_len: int = 50) -> str:
    """Summarize text to max length."""
    if not text:
        return ""
    text = str(text).replace("\n", " ").strip()
    if len(text) > max_len:
        return text[:max_len-3] + "..."
    return text


def _run_tracked_task(
    task: str,
    tools: List,
    max_iterations: int,
    model: Optional[str],
    verbose: bool,
    step_callback: Optional[callable] = None,
    auto_approve: bool = True,
) -> TrackerResult:
    """Run a task with step tracking using centralized autonomy system.
    
    Args:
        task: The task to execute
        tools: List of tool functions to use
        max_iterations: Maximum autonomous iterations
        model: LLM model to use (optional)
        verbose: Show verbose output
        step_callback: Callback for each step (optional)
        auto_approve: Auto-approve all tool calls (default: True)
    """
    from praisonaiagents import Agent
    
    # ========================================================================
    # AUTO-APPROVE: Set env var so @require_approval decorators on tool
    # functions (execute_code, execute_command, write_file, etc.) auto-approve.
    # The decorator checks PRAISONAI_AUTO_APPROVE env var independently of
    # the Agent's approval= parameter.
    # ========================================================================
    prev_auto_approve = os.environ.get("PRAISONAI_AUTO_APPROVE")
    if auto_approve:
        os.environ["PRAISONAI_AUTO_APPROVE"] = "true"
    
    steps: List[TrackedStep] = []
    tools_used: set = set()
    start_time = time.time()
    step_number = 0
    
    # ========================================================================
    # CENTRALIZED AUTONOMY CONFIGURATION
    # Uses full_auto level with auto-approval for autonomous tracking
    # ========================================================================
    agent_kwargs = {
        "name": "tracker_agent",
        "instructions": """You are an autonomous agent with access to various tools.
You MUST use tools to complete tasks - do NOT rely on your training knowledge alone.

TOOL USAGE RULES:
- For research/search tasks: use search_web or internet_search
- For file operations: use read_file, write_file, list_files
- For code tasks: use execute_code, analyze_code
- For shell commands: use execute_command
- For web scraping: use web_crawl, scrape_page, extract_text

When you have fully completed the task, say 'Task completed' or 'Done'.""",
        "tools": tools,
        # Centralized autonomy configuration
        "autonomy": {
            "enabled": True,
            "level": "full_auto",  # Full autonomous mode
            "max_iterations": max_iterations,
            "doom_loop_threshold": 5,
            "auto_escalate": True,
        },
        # Auto-approve all tools for tracker (agent-centric approval)
        "approval": auto_approve,
    }
    
    if model:
        agent_kwargs["llm"] = model
    
    if not verbose:
        agent_kwargs["output"] = "silent"
    
    agent = Agent(**agent_kwargs)
    
    # Wrap execute_tool to track tool calls
    original_execute_tool = agent.execute_tool
    
    def tracked_execute_tool(tool_name, *args, **kwargs):
        nonlocal step_number
        step_number += 1
        step_start = time.time()
        tools_used.add(tool_name)
        
        try:
            result = original_execute_tool(tool_name, *args, **kwargs)
            duration = time.time() - step_start
            
            step = TrackedStep(
                step_number=step_number,
                timestamp=datetime.now().isoformat(),
                action_type="tool_call",
                action_name=tool_name,
                input_summary=_summarize_text(str(args) + str(kwargs)),
                output_summary=_summarize_text(str(result)),
                duration_seconds=duration,
                success=True,
            )
            steps.append(step)
            if step_callback:
                step_callback(step)
            return result
        except Exception as e:
            duration = time.time() - step_start
            step = TrackedStep(
                step_number=step_number,
                timestamp=datetime.now().isoformat(),
                action_type="tool_error",
                action_name=tool_name,
                input_summary=_summarize_text(str(args) + str(kwargs)),
                output_summary="",
                duration_seconds=duration,
                success=False,
                error=str(e),
            )
            steps.append(step)
            if step_callback:
                step_callback(step)
            raise
    
    agent.execute_tool = tracked_execute_tool
    
    # Track chat calls
    original_chat = agent.chat
    
    def tracked_chat(prompt, *args, **kwargs):
        nonlocal step_number
        step_number += 1
        step_start = time.time()
        
        try:
            result = original_chat(prompt, *args, **kwargs)
            duration = time.time() - step_start
            
            # Record step
            step = TrackedStep(
                step_number=step_number,
                timestamp=datetime.now().isoformat(),
                action_type="chat",
                action_name="thinking",
                input_summary=_summarize_text(prompt),
                output_summary=_summarize_text(str(result)),
                duration_seconds=duration,
                success=True,
            )
            steps.append(step)
            
            if step_callback:
                step_callback(step)
            
            return result
        except Exception as e:
            duration = time.time() - step_start
            step = TrackedStep(
                step_number=step_number,
                timestamp=datetime.now().isoformat(),
                action_type="error",
                action_name="chat_error",
                input_summary=_summarize_text(prompt),
                output_summary="",
                duration_seconds=duration,
                success=False,
                error=str(e),
            )
            steps.append(step)
            if step_callback:
                step_callback(step)
            raise
    
    agent.chat = tracked_chat
    
    # Run autonomous loop
    try:
        result = agent.run_autonomous(
            prompt=task,
            max_iterations=max_iterations,
        )
        
        total_duration = time.time() - start_time
        
        # Extract tool usage from AutonomyResult.actions
        if hasattr(result, 'actions') and result.actions:
            for action in result.actions:
                if isinstance(action, dict):
                    action_type = action.get('type', 'unknown')
                    action_name = action.get('name', action.get('tool', 'unknown'))
                    if action_type == 'tool_call' or 'tool' in action:
                        tools_used.add(action_name)
        
        # Analyze gaps
        gaps = []
        if result.iterations >= max_iterations:
            gaps.append("Hit max iterations - task may be incomplete")
        if result.completion_reason == "doom_loop":
            gaps.append("Doom loop detected - agent repeated same actions")
        if result.completion_reason == "needs_help":
            gaps.append("Agent requested human help")
        if not tools_used and len(tools) > 0:
            gaps.append("No tools were used despite being available")
        
        return TrackerResult(
            task=task,
            success=result.success,
            completion_reason=result.completion_reason,
            total_steps=len(steps) if steps else result.iterations,
            total_duration=total_duration,
            steps=steps,
            tools_used=list(tools_used),
            gaps_identified=gaps,
        )
        
    except Exception as e:
        total_duration = time.time() - start_time
        return TrackerResult(
            task=task,
            success=False,
            completion_reason="error",
            total_steps=len(steps),
            total_duration=total_duration,
            steps=steps,
            tools_used=list(tools_used),
            gaps_identified=[f"Error: {str(e)}"],
        )
    finally:
        # Restore original PRAISONAI_AUTO_APPROVE env var
        if prev_auto_approve is None:
            os.environ.pop("PRAISONAI_AUTO_APPROVE", None)
        else:
            os.environ["PRAISONAI_AUTO_APPROVE"] = prev_auto_approve


def _print_step_table(steps: List[TrackedStep]) -> None:
    """Print a table of all steps."""
    table = Table(title="📊 Execution Steps", show_header=True, header_style="bold cyan")
    table.add_column("#", style="dim", width=4)
    table.add_column("Type", width=10)
    table.add_column("Action", width=15)
    table.add_column("Input", width=30)
    table.add_column("Output", width=30)
    table.add_column("Time", width=8)
    table.add_column("Status", width=8)
    
    for step in steps:
        status = "✅" if step.success else "❌"
        table.add_row(
            str(step.step_number),
            step.action_type,
            step.action_name,
            step.input_summary,
            step.output_summary,
            f"{step.duration_seconds:.2f}s",
            status,
        )
    
    console.print(table)


def _print_summary(result: TrackerResult) -> None:
    """Print execution summary."""
    status_icon = "✅" if result.success else "❌"
    
    console.print(Panel(
        f"""
[bold]{status_icon} Task: {_summarize_text(result.task, 60)}[/bold]

[cyan]Completion Reason:[/cyan] {result.completion_reason}
[cyan]Total Steps:[/cyan] {result.total_steps}
[cyan]Total Duration:[/cyan] {result.total_duration:.2f}s
[cyan]Tools Used:[/cyan] {', '.join(result.tools_used) if result.tools_used else 'None'}
""",
        title="📋 Execution Summary",
        border_style="green" if result.success else "red",
    ))
    
    if result.gaps_identified:
        console.print("\n[bold yellow]⚠️ Gaps Identified:[/bold yellow]")
        for gap in result.gaps_identified:
            console.print(f"  • {gap}")


@app.callback(invoke_without_command=True)
def tracker_main(
    ctx: typer.Context,
    task: Optional[str] = typer.Argument(None, help="Task for the agent to complete"),
    max_iterations: int = typer.Option(20, "--max-iterations", "-n", help="Maximum iterations (default: 20)"),
    model: Optional[str] = typer.Option(None, "--model", "-m", help="LLM model to use"),
    tools: Optional[str] = typer.Option(None, "--tools", "-t", help="Comma-separated tool names to use"),
    extended: bool = typer.Option(False, "--extended", "-e", help="Include extended tools (may require API keys)"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show verbose output"),
    live: bool = typer.Option(True, "--live/--no-live", help="Show live step updates (default: on)"),
):
    """Run an agent with step-by-step tracking.
    
    The tracker runs an agent in autonomous mode and records every step,
    tool call, and decision. At the end, it displays a summary table
    showing all steps taken and any gaps identified.
    
    Examples:
    
        praisonai tracker "Search for Python best practices and summarize"
        
        praisonai tracker "Read config.yaml and explain its structure" -v
        
        praisonai tracker "Find trending AI news" --tools search_web,web_crawl
    """
    if ctx.invoked_subcommand is not None:
        return
    
    if not task:
        typer.echo(ctx.get_help())
        return
    
    # Resolve tools
    tool_names = AUTONOMY_DEFAULT_TOOLS.copy()
    if extended:
        tool_names.extend(EXTENDED_TOOLS)
    if tools:
        # Override with user-specified tools
        tool_names = [t.strip() for t in tools.split(",")]
    
    resolved_tools = _get_tools(tool_names)
    
    console.print(f"\n[bold cyan]🔍 Agent Tracker[/bold cyan]")
    console.print(f"[dim]Task: {_summarize_text(task, 70)}[/dim]")
    console.print(f"[dim]Tools: {len(resolved_tools)} loaded ({', '.join(tool_names[:5])}{'...' if len(tool_names) > 5 else ''})[/dim]")
    console.print(f"[dim]Max iterations: {max_iterations}[/dim]\n")
    
    # Step callback for live updates
    def step_callback(step: TrackedStep):
        if live:
            status = "✅" if step.success else "❌"
            console.print(f"  [{step.step_number}] {status} {step.action_type}: {step.action_name} ({step.duration_seconds:.2f}s)")
    
    # Run tracked task
    with console.status("[bold green]Running autonomous agent...[/bold green]") if not live else console:
        result = _run_tracked_task(
            task=task,
            tools=resolved_tools,
            max_iterations=max_iterations,
            model=model,
            verbose=verbose,
            step_callback=step_callback if live else None,
        )
    
    # Print results
    console.print("\n")
    _print_step_table(result.steps)
    console.print("\n")
    _print_summary(result)


@app.command(name="batch")
def tracker_batch(
    tasks_file: str = typer.Argument(..., help="JSON file with list of tasks"),
    max_iterations: int = typer.Option(20, "--max-iterations", "-n", help="Maximum iterations per task"),
    model: Optional[str] = typer.Option(None, "--model", "-m", help="LLM model to use"),
    output: Optional[str] = typer.Option(None, "--output", "-o", help="Output JSON file for results"),
):
    """Run multiple tasks and generate a comparison table.
    
    The tasks file should be a JSON array of task strings:
    
        ["Task 1", "Task 2", "Task 3"]
    
    Example:
    
        praisonai tracker batch tasks.json -o results.json
    """
    import json
    
    try:
        with open(tasks_file) as f:
            tasks = json.load(f)
    except Exception as e:
        console.print(f"[red]Error reading tasks file: {e}[/red]")
        raise typer.Exit(1)
    
    if not isinstance(tasks, list):
        console.print("[red]Tasks file must contain a JSON array of strings[/red]")
        raise typer.Exit(1)
    
    console.print(f"\n[bold cyan]🔍 Batch Agent Tracker[/bold cyan]")
    console.print(f"[dim]Running {len(tasks)} tasks...[/dim]\n")
    
    resolved_tools = _get_tools(AUTONOMY_DEFAULT_TOOLS)
    results: List[TrackerResult] = []
    
    for i, task in enumerate(tasks, 1):
        console.print(f"\n[bold]Task {i}/{len(tasks)}:[/bold] {_summarize_text(task, 50)}")
        
        result = _run_tracked_task(
            task=task,
            tools=resolved_tools,
            max_iterations=max_iterations,
            model=model,
            verbose=False,
            step_callback=None,
        )
        results.append(result)
        
        status = "✅" if result.success else "❌"
        console.print(f"  {status} {result.completion_reason} ({result.total_steps} steps, {result.total_duration:.2f}s)")
    
    # Print summary table
    console.print("\n")
    table = Table(title="📊 Batch Results Summary", show_header=True, header_style="bold cyan")
    table.add_column("#", style="dim", width=4)
    table.add_column("Task", width=40)
    table.add_column("Status", width=8)
    table.add_column("Reason", width=15)
    table.add_column("Steps", width=6)
    table.add_column("Duration", width=10)
    table.add_column("Gaps", width=20)
    
    for i, result in enumerate(results, 1):
        status = "✅" if result.success else "❌"
        gaps = ", ".join(result.gaps_identified[:2]) if result.gaps_identified else "-"
        table.add_row(
            str(i),
            _summarize_text(result.task, 40),
            status,
            result.completion_reason,
            str(result.total_steps),
            f"{result.total_duration:.2f}s",
            _summarize_text(gaps, 20),
        )
    
    console.print(table)
    
    # Calculate stats
    success_count = sum(1 for r in results if r.success)
    total_steps = sum(r.total_steps for r in results)
    total_duration = sum(r.total_duration for r in results)
    
    console.print(f"\n[bold]Summary:[/bold]")
    console.print(f"  Success rate: {success_count}/{len(results)} ({100*success_count/len(results):.1f}%)")
    console.print(f"  Total steps: {total_steps}")
    console.print(f"  Total duration: {total_duration:.2f}s")
    
    # Save results if output specified
    if output:
        output_data = {
            "tasks": len(results),
            "success_rate": success_count / len(results),
            "total_steps": total_steps,
            "total_duration": total_duration,
            "results": [
                {
                    "task": r.task,
                    "success": r.success,
                    "completion_reason": r.completion_reason,
                    "steps": r.total_steps,
                    "duration": r.total_duration,
                    "gaps": r.gaps_identified,
                }
                for r in results
            ],
        }
        with open(output, "w") as f:
            json.dump(output_data, f, indent=2)
        console.print(f"\n[green]Results saved to {output}[/green]")


@app.command(name="tools")
def tracker_tools():
    """List all available tools for the tracker."""
    console.print("\n[bold cyan]🛠️ Available Tools[/bold cyan]\n")
    
    console.print("[bold]Default Tools (no API keys required):[/bold]")
    for tool in AUTONOMY_DEFAULT_TOOLS:
        console.print(f"  • {tool}")
    
    console.print("\n[bold]Extended Tools (may require API keys):[/bold]")
    for tool in EXTENDED_TOOLS:
        console.print(f"  • {tool}")
    
    console.print("\n[dim]Use --tools to specify custom tools, e.g.:[/dim]")
    console.print("[dim]  praisonai tracker 'task' --tools search_web,read_file[/dim]")
