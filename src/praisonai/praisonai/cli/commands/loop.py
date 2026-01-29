"""
Loop command for autonomous agent execution.

Provides CLI interface for running agents in autonomous loops with:
- Completion promise detection
- Context clearing between iterations
- Iteration limits and timeouts
"""

from typing import Optional

import typer

app = typer.Typer(
    name="loop",
    help="Run agents in autonomous execution loops",
    no_args_is_help=False,
)


@app.callback(invoke_without_command=True)
def loop_main(
    ctx: typer.Context,
    prompt: Optional[str] = typer.Argument(None, help="Task prompt for the agent"),
    max_iterations: int = typer.Option(10, "--max-iterations", "-n", help="Maximum iterations (default: 10)"),
    completion_promise: Optional[str] = typer.Option(None, "--completion-promise", "-p", help="Promise text to signal completion"),
    clear_context: bool = typer.Option(False, "--clear-context", "-c", help="Clear chat history between iterations"),
    timeout: Optional[float] = typer.Option(None, "--timeout", "-t", help="Timeout in seconds"),
    model: Optional[str] = typer.Option(None, "--model", "-m", help="LLM model to use"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show verbose output"),
):
    """Run an agent in an autonomous loop.
    
    The agent will execute the given PROMPT repeatedly until:
    - It outputs <promise>TEXT</promise> matching --completion-promise
    - It reaches --max-iterations
    - It times out (if --timeout is set)
    - It detects a doom loop (repeated actions)
    
    Examples:
    
        praisonai loop "Build a REST API" -n 5
        
        praisonai loop "Refactor auth module" -p DONE
        
        praisonai loop "Implement feature X" -p COMPLETE -c
    """
    if ctx.invoked_subcommand is not None:
        return
    
    if not prompt:
        typer.echo(ctx.get_help())
        return
    
    _run_loop(
        prompt=prompt,
        max_iterations=max_iterations,
        completion_promise=completion_promise,
        clear_context=clear_context,
        timeout=timeout,
        model=model,
        verbose=verbose,
    )


def _run_loop(
    prompt: str,
    max_iterations: int,
    completion_promise: Optional[str],
    clear_context: bool,
    timeout: Optional[float],
    model: Optional[str],
    verbose: bool,
):
    """Execute the autonomous loop."""
    try:
        from praisonaiagents import Agent
    except ImportError:
        typer.echo("Error: praisonaiagents not installed. Run: pip install praisonaiagents", err=True)
        raise typer.Exit(1)
    
    # Build autonomy config
    autonomy_config = {
        "max_iterations": max_iterations,
        "completion_promise": completion_promise,
        "clear_context": clear_context,
    }
    
    # Create agent
    agent_kwargs = {
        "name": "loop_agent",
        "instructions": "You are an autonomous agent. Complete the given task. "
                       "When you have fully completed the task, signal completion.",
        "autonomy": autonomy_config,
    }
    
    if model:
        agent_kwargs["llm"] = model
    
    if not verbose:
        agent_kwargs["output"] = "silent"
    
    # Add completion promise instructions if provided
    if completion_promise:
        agent_kwargs["instructions"] += (
            f"\n\nIMPORTANT: When you have completed the task, you MUST include "
            f"<promise>{completion_promise}</promise> in your response to signal completion."
        )
    
    agent = Agent(**agent_kwargs)
    
    # Show configuration
    if verbose:
        typer.echo("🔄 Starting autonomous loop")
        typer.echo(f"   Prompt: {prompt[:50]}{'...' if len(prompt) > 50 else ''}")
        typer.echo(f"   Max iterations: {max_iterations}")
        if completion_promise:
            typer.echo(f"   Completion promise: <promise>{completion_promise}</promise>")
        if clear_context:
            typer.echo("   Context clearing: enabled")
        if timeout:
            typer.echo(f"   Timeout: {timeout}s")
        typer.echo("")
    
    # Run autonomous loop
    try:
        result = agent.run_autonomous(
            prompt=prompt,
            max_iterations=max_iterations,
            timeout_seconds=timeout,
            completion_promise=completion_promise,
            clear_context=clear_context,
        )
        
        # Display result
        if result.success:
            typer.echo("✅ Task completed successfully")
            typer.echo(f"   Reason: {result.completion_reason}")
            typer.echo(f"   Iterations: {result.iterations}")
            typer.echo(f"   Duration: {result.duration_seconds:.2f}s")
            if result.started_at:
                typer.echo(f"   Started: {result.started_at}")
            if verbose:
                typer.echo(f"\n📝 Final output:\n{result.output}")
        else:
            typer.echo("❌ Task did not complete")
            typer.echo(f"   Reason: {result.completion_reason}")
            typer.echo(f"   Iterations: {result.iterations}")
            typer.echo(f"   Duration: {result.duration_seconds:.2f}s")
            if result.started_at:
                typer.echo(f"   Started: {result.started_at}")
            if result.error:
                typer.echo(f"   Error: {result.error}")
            raise typer.Exit(1)
            
    except KeyboardInterrupt:
        typer.echo("\n⚠️  Loop cancelled by user")
        raise typer.Exit(130)
    except typer.Exit:
        raise
    except Exception as e:
        typer.echo(f"❌ Error: {e}", err=True)
        raise typer.Exit(1)


@app.command(name="help")
def loop_help():
    """Show detailed help for the loop command."""
    typer.echo("""
🔄 Autonomous Loop Command

The loop command runs an agent in an autonomous execution loop,
similar to Ralph's self-referential development loop.

FEATURES:
  • Completion Promise: Agent signals "done" with <promise>TEXT</promise>
  • Context Clearing: Fresh memory each iteration (file-based state)
  • Iteration Limits: Prevent runaway loops
  • Doom Loop Detection: Stops on repeated actions

USAGE:
  praisonai loop "Your task here" [OPTIONS]

OPTIONS:
  -n, --max-iterations INT     Maximum iterations (default: 10)
  -p, --completion-promise STR Promise text to signal completion
  -c, --clear-context          Clear chat history between iterations
  -t, --timeout FLOAT          Timeout in seconds
  -m, --model STR              LLM model to use
  -v, --verbose                Show verbose output

EXAMPLES:
  # Basic loop
  praisonai loop "Build a calculator" -n 5

  # With completion promise
  praisonai loop "Refactor the auth module" -p DONE -v

  # With context clearing (forces file-based state)
  praisonai loop "Implement feature X" -p COMPLETE -c -n 20

  # With timeout
  praisonai loop "Debug the issue" -t 300 -v
""")
