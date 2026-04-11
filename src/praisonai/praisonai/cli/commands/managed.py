"""
Managed Agents command group for PraisonAI CLI.

Provides commands for Anthropic Managed Agents (cloud-hosted agent backend).
"""

from typing import Optional

import typer

app = typer.Typer(help="Managed Agents (Anthropic cloud-hosted backend)")


@app.callback(invoke_without_command=True)
def managed_main(
    ctx: typer.Context,
    prompt: Optional[str] = typer.Argument(None, help="Prompt to send to the managed agent"),
    model: Optional[str] = typer.Option(None, "--model", "-m", help="Model to use (default: claude-haiku-4-5)"),
    system: Optional[str] = typer.Option(None, "--system", "-s", help="System prompt"),
    name: Optional[str] = typer.Option(None, "--name", "-n", help="Agent name"),
    stream: bool = typer.Option(False, "--stream", help="Stream response token by token"),
    packages: Optional[str] = typer.Option(None, "--packages", "-p", help="Comma-separated pip packages to install"),
    networking: bool = typer.Option(True, "--networking/--no-networking", help="Enable unrestricted networking"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output"),
):
    """
    Run a prompt on Anthropic Managed Agents.

    Uses sensible defaults — zero config needed:
      name="Agent", model="claude-haiku-4-5",
      system="You are a helpful coding assistant."

    Examples:
        praisonai managed "Say hello"
        praisonai managed "Write fibonacci" --model claude-sonnet-4-6
        praisonai managed "Analyze data" --packages pandas,numpy
        praisonai managed --stream "Explain Python decorators"
    """
    if ctx.invoked_subcommand is not None:
        return

    if not prompt:
        typer.echo("Usage: praisonai managed \"your prompt\"")
        typer.echo("       praisonai managed --help")
        raise typer.Exit(0)

    try:
        from praisonai import Agent, ManagedAgent, ManagedConfig
    except ImportError:
        typer.echo("Error: praisonai with managed agents support is required.")
        typer.echo("Install with: pip install 'praisonai[managed]'")
        raise typer.Exit(1)

    # Build config only with non-default values
    cfg_kwargs = {}
    if model:
        cfg_kwargs["model"] = model
    if system:
        cfg_kwargs["system"] = system
    if name:
        cfg_kwargs["name"] = name
    if packages:
        cfg_kwargs["packages"] = {"pip": [p.strip() for p in packages.split(",")]}
    if not networking:
        cfg_kwargs["networking"] = {"type": "limited"}

    # Create agent — zero config works, overrides applied if given
    if cfg_kwargs:
        managed = ManagedAgent(config=ManagedConfig(**cfg_kwargs))
    else:
        managed = ManagedAgent()

    agent = Agent(name=name or "managed-agent", backend=managed)

    if verbose:
        typer.echo(f"Model: {managed._cfg.get('model', 'claude-haiku-4-5')}")
        typer.echo(f"System: {managed._cfg.get('system', 'You are a helpful coding assistant.')}")
        if packages:
            typer.echo(f"Packages: {packages}")
        typer.echo("")

    result = agent.start(prompt)

    if result:
        print(result)

    if verbose:
        typer.echo(f"\nAgent ID: {managed.agent_id}")
        typer.echo(f"Session ID: {managed.managed_session_id}")
        typer.echo(f"Input tokens: {managed.total_input_tokens}")
        typer.echo(f"Output tokens: {managed.total_output_tokens}")


@app.command("multi")
def managed_multi(
    model: Optional[str] = typer.Option(None, "--model", "-m", help="Model to use"),
    system: Optional[str] = typer.Option(None, "--system", "-s", help="System prompt"),
    name: Optional[str] = typer.Option(None, "--name", "-n", help="Agent name"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output"),
):
    """
    Start multi-turn conversation with a managed agent.

    Examples:
        praisonai managed multi
        praisonai managed multi --model claude-sonnet-4-6
    """
    try:
        from praisonai import Agent, ManagedAgent, ManagedConfig
    except ImportError:
        typer.echo("Error: praisonai with managed agents support is required.")
        raise typer.Exit(1)

    cfg_kwargs = {}
    if model:
        cfg_kwargs["model"] = model
    if system:
        cfg_kwargs["system"] = system
    if name:
        cfg_kwargs["name"] = name

    if cfg_kwargs:
        managed = ManagedAgent(config=ManagedConfig(**cfg_kwargs))
    else:
        managed = ManagedAgent()

    agent = Agent(name=name or "managed-agent", backend=managed)

    typer.echo("Managed Agent multi-turn session (type 'exit' or 'quit' to stop)")
    typer.echo(f"Model: {managed._cfg.get('model', 'claude-haiku-4-5')}")
    typer.echo("")

    turn = 0
    while True:
        try:
            user_input = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            typer.echo("\nSession ended.")
            break

        if user_input.lower() in ("exit", "quit", "q"):
            typer.echo("Session ended.")
            break

        if not user_input:
            continue

        turn += 1
        result = agent.start(user_input)
        if result:
            print(f"\nAgent: {result}\n")

    if verbose:
        typer.echo(f"\nTurns: {turn}")
        typer.echo(f"Input tokens: {managed.total_input_tokens}")
        typer.echo(f"Output tokens: {managed.total_output_tokens}")
