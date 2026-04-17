"""
Managed Agents command group for PraisonAI CLI.

Provides commands for Anthropic Managed Agents (cloud-hosted agent backend).

Sub-command groups:
  praisonai managed "prompt"          — run a single prompt
  praisonai managed multi             — interactive multi-turn chat
  praisonai managed sessions ...      — list / get / resume sessions
  praisonai managed agents ...        — list / get / update agents
  praisonai managed envs ...          — list / get environments
  praisonai managed ids ...           — save / restore / show ID snapshots
"""

import json
import pathlib
from typing import Optional

import typer

app = typer.Typer(help="Managed Agents (Anthropic cloud or local provider)")

# ── sub-app registrations (defined below, registered after) ──
sessions_app = typer.Typer(help="Manage sessions")
agents_app   = typer.Typer(help="Manage agents")
envs_app     = typer.Typer(help="Manage environments")
ids_app      = typer.Typer(help="Save / restore assigned IDs")


@app.callback()
def managed_callback(ctx: typer.Context):
    """Managed Agents — Anthropic cloud-hosted backend.

    Run a prompt:
        praisonai managed run "Say hello"
        praisonai managed run --stream "Explain decorators"

    Manage resources:
        praisonai managed sessions list agent_01...
        praisonai managed agents list
        praisonai managed envs list
        praisonai managed ids show
    """


def _build_managed(
    provider: Optional[str] = None,
    model: Optional[str] = None,
    system: Optional[str] = None,
    name: Optional[str] = None,
    packages: Optional[str] = None,
    networking: bool = True,
    database_url: Optional[str] = None,
):
    """Build a ManagedAgent instance from CLI arguments."""
    try:
        from praisonai import ManagedAgent, ManagedConfig
    except ImportError:
        typer.echo("Error: praisonai with managed agents support is required.")
        typer.echo("Install with: pip install 'praisonai[managed]'")
        raise typer.Exit(1)

    # Build DB adapter if --db URL was provided
    db_adapter = None
    if database_url:
        from praisonai import DB
        db_adapter = DB(database_url=database_url)

    # Determine effective provider
    resolved_provider = provider
    if resolved_provider is None:
        import os
        if os.getenv("ANTHROPIC_API_KEY") or os.getenv("CLAUDE_API_KEY"):
            resolved_provider = "anthropic"
        else:
            resolved_provider = "local"

    if resolved_provider == "anthropic":
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
        config = ManagedConfig(**cfg_kwargs) if cfg_kwargs else None
        return ManagedAgent(provider="anthropic", config=config, db=db_adapter)
    else:
        from praisonai import LocalManagedConfig
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
        config = LocalManagedConfig(**cfg_kwargs) if cfg_kwargs else None
        return ManagedAgent(provider=resolved_provider, config=config, db=db_adapter)


@app.command("run")
def managed_main(
    prompt: str = typer.Argument(..., help="Prompt to send to the managed agent"),
    model: Optional[str] = typer.Option(None, "--model", "-m", help="Model to use"),
    system: Optional[str] = typer.Option(None, "--system", "-s", help="System prompt"),
    name: Optional[str] = typer.Option(None, "--name", "-n", help="Agent name"),
    stream: bool = typer.Option(False, "--stream", help="Stream response token by token"),
    packages: Optional[str] = typer.Option(None, "--packages", "-p", help="Comma-separated pip packages to install"),
    networking: bool = typer.Option(True, "--networking/--no-networking", help="Enable unrestricted networking"),
    provider: Optional[str] = typer.Option(None, "--provider", help="Provider: anthropic, local, openai, ollama, gemini (auto-detects if not set)"),
    database_url: Optional[str] = typer.Option(None, "--db", help="Database URL for persistence (e.g. sqlite:///data.db, postgresql://...)"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output"),
):
    """Run a single prompt on a managed agent.

    Auto-detects provider: Anthropic if ANTHROPIC_API_KEY is set, local otherwise.
    Use --provider to override.

    Examples:
        praisonai managed run "Say hello"
        praisonai managed run "Write fibonacci" --model claude-sonnet-4-6
        praisonai managed run "Analyze data" --provider local --model gpt-4o
        praisonai managed run --stream --provider ollama --model llama3 "Explain decorators"
    """
    managed = _build_managed(provider=provider, model=model, system=system, name=name, packages=packages, networking=networking, database_url=database_url)

    from praisonai import Agent
    agent = Agent(name=name or "managed-agent", backend=managed)

    if verbose:
        typer.echo(f"Provider: {managed.provider}")
        typer.echo(f"Model: {managed._cfg.get('model', 'unknown')}")
        typer.echo(f"System: {managed._cfg.get('system', 'default')}")
        if packages:
            typer.echo(f"Packages: {packages}")
        if database_url:
            typer.echo(f"DB: {database_url}")
        typer.echo("")

    result = agent.start(prompt, stream=stream)

    if result and not stream:
        print(result)

    if verbose:
        typer.echo(f"\nAgent ID: {managed.agent_id}")
        typer.echo(f"Session ID: {getattr(managed, 'session_id', None)}")
        typer.echo(f"Input tokens: {managed.total_input_tokens}")
        typer.echo(f"Output tokens: {managed.total_output_tokens}")


@app.command("multi")
def managed_multi(
    model: Optional[str] = typer.Option(None, "--model", "-m", help="Model to use"),
    system: Optional[str] = typer.Option(None, "--system", "-s", help="System prompt"),
    name: Optional[str] = typer.Option(None, "--name", "-n", help="Agent name"),
    provider: Optional[str] = typer.Option(None, "--provider", help="Provider: anthropic, local, openai, ollama, gemini"),
    database_url: Optional[str] = typer.Option(None, "--db", help="Database URL for persistence (e.g. sqlite:///data.db, postgresql://...)"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output"),
):
    """
    Start multi-turn conversation with a managed agent.

    Examples:
        praisonai managed multi
        praisonai managed multi --model claude-sonnet-4-6
        praisonai managed multi --provider local --model gpt-4o
    """
    managed = _build_managed(provider=provider, model=model, system=system, name=name, database_url=database_url)

    from praisonai import Agent
    agent = Agent(name=name or "managed-agent", backend=managed)

    typer.echo(f"Managed Agent multi-turn session — provider: {managed.provider} (type 'exit' to stop)")
    typer.echo(f"Model: {managed._cfg.get('model', 'default')}")
    if database_url:
        typer.echo(f"DB: {database_url}")
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
        result = agent.start(user_input, stream=True)
        if result:
            print(f"\nAgent: {result}\n")

    if verbose:
        typer.echo(f"\nTurns: {turn}")
        typer.echo(f"Input tokens: {managed.total_input_tokens}")
        typer.echo(f"Output tokens: {managed.total_output_tokens}")


# ─────────────────────────────────────────────────────────────────────────────
# sessions sub-commands
# ─────────────────────────────────────────────────────────────────────────────

def _get_client():
    """Return an Anthropic client using env API key."""
    try:
        import anthropic
    except ImportError:
        import sys

        typer.echo(
            "Error: the anthropic package is not installed for the Python running this CLI.\n"
            f"  Interpreter: {sys.executable}\n"
            "Fix either:\n"
            "  • pip install 'anthropic>=0.94.0' into that environment, or\n"
            "  • use the same interpreter that already has anthropic, e.g.\n"
            "      python -m praisonai managed envs list"
        )
        raise typer.Exit(1)
    import os
    api_key = os.getenv("ANTHROPIC_API_KEY") or os.getenv("CLAUDE_API_KEY")
    if not api_key:
        typer.echo("Error: ANTHROPIC_API_KEY not set.")
        raise typer.Exit(1)
    return anthropic.Anthropic(api_key=api_key)


@sessions_app.command("list")
def sessions_list(
    agent_id: str = typer.Argument(..., help="Agent ID (agent_01...)"),
    limit: int = typer.Option(10, "--limit", "-l", help="Max sessions to return"),
):
    """List sessions for a given agent ID.

    Example:
        praisonai managed sessions list agent_01AbCdEf
    """
    client = _get_client()
    sessions = client.beta.sessions.list(agent_id=agent_id, limit=limit)
    rows = getattr(sessions, "data", sessions)
    if not rows:
        typer.echo("No sessions found.")
        return
    typer.echo(f"{'ID':<40} {'STATUS':<10} TITLE")
    typer.echo("-" * 70)
    for s in rows:
        typer.echo(f"{s.id:<40} {getattr(s,'status',''):<10} {getattr(s,'title','')}")


@sessions_app.command("get")
def sessions_get(
    session_id: str = typer.Argument(..., help="Session ID (sesn_01...)"),
):
    """Get details and usage for a session.

    Example:
        praisonai managed sessions get sesn_01AbCdEf
    """
    client = _get_client()
    sess = client.beta.sessions.retrieve(session_id)
    typer.echo(f"ID      : {sess.id}")
    typer.echo(f"Status  : {getattr(sess, 'status', 'unknown')}")
    typer.echo(f"Title   : {getattr(sess, 'title', '')}")
    usage = getattr(sess, "usage", None)
    if usage:
        typer.echo(f"Input tokens : {getattr(usage, 'input_tokens', 0)}")
        typer.echo(f"Output tokens: {getattr(usage, 'output_tokens', 0)}")


@sessions_app.command("resume")
def sessions_resume(
    session_id: str = typer.Argument(..., help="Session ID to resume (sesn_01...)"),
    prompt: str = typer.Argument(..., help="Prompt to send to the resumed session"),
    stream: bool = typer.Option(True, "--stream/--no-stream", help="Stream response"),
    model: Optional[str] = typer.Option(None, "--model", "-m", help="Model (only used if agent needs re-creating)"),
    system: Optional[str] = typer.Option(None, "--system", "-s", help="System prompt override"),
):
    """Resume an existing session by ID and send a prompt.

    Example:
        praisonai managed sessions resume sesn_01AbCdEf "Continue the task"
        praisonai managed sessions resume sesn_01AbCdEf "What did we do?" --stream
    """
    try:
        from praisonai import Agent, ManagedAgent, ManagedConfig
    except ImportError:
        typer.echo("Error: pip install praisonai")
        raise typer.Exit(1)

    cfg_kwargs = {}
    if model:
        cfg_kwargs["model"] = model
    if system:
        cfg_kwargs["system"] = system

    managed = ManagedAgent(config=ManagedConfig(**cfg_kwargs) if cfg_kwargs else None)
    managed.resume_session(session_id)

    agent = Agent(name="managed-agent", backend=managed)
    result = agent.start(prompt, stream=stream)
    if result and not stream:
        print(result)


@sessions_app.command("delete")
def sessions_delete(
    session_id: str = typer.Argument(..., help="Session ID to delete (sesn_01...)"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt"),
):
    """Delete a session.

    Example:
        praisonai managed sessions delete sesn_01AbCdEf
        praisonai managed sessions delete sesn_01AbCdEf --yes
    """
    if not yes:
        confirm = typer.confirm(f"Are you sure you want to delete session {session_id}?")
        if not confirm:
            typer.echo("Deletion cancelled.")
            raise typer.Exit(0)

    client = _get_client()
    try:
        client.beta.sessions.delete(session_id)
        typer.echo(f"Session {session_id} deleted successfully.")
    except Exception as e:
        typer.echo(f"Error deleting session: {e}")
        raise typer.Exit(1)


# ─────────────────────────────────────────────────────────────────────────────
# agents sub-commands
# ─────────────────────────────────────────────────────────────────────────────

@agents_app.command("list")
def agents_list(
    limit: int = typer.Option(10, "--limit", "-l", help="Max agents to return"),
):
    """List managed agents on your Anthropic account.

    Example:
        praisonai managed agents list
        praisonai managed agents list --limit 20
    """
    client = _get_client()
    agents = client.beta.agents.list(limit=limit)
    rows = getattr(agents, "data", agents)
    if not rows:
        typer.echo("No agents found.")
        return
    typer.echo(f"{'ID':<40} {'VER':<5} {'MODEL':<25} NAME")
    typer.echo("-" * 85)
    for a in rows:
        model_obj = getattr(a, 'model', '')
        model_str = getattr(model_obj, 'id', str(model_obj))
        typer.echo(
            f"{a.id:<40} {str(getattr(a,'version','')):<5} "
            f"{model_str:<25} {getattr(a,'name','')}"
        )


@agents_app.command("get")
def agents_get(
    agent_id: str = typer.Argument(..., help="Agent ID (agent_01...)"),
):
    """Get details for a specific agent.

    Example:
        praisonai managed agents get agent_01AbCdEf
    """
    client = _get_client()
    a = client.beta.agents.retrieve(agent_id)
    typer.echo(f"ID     : {a.id}")
    typer.echo(f"Name   : {getattr(a, 'name', '')}")
    model_obj = getattr(a, 'model', '')
    typer.echo(f"Model  : {getattr(model_obj, 'id', str(model_obj))}")
    typer.echo(f"Version: {getattr(a, 'version', '')}")
    typer.echo(f"System : {getattr(a, 'system', '')[:120]}")


@agents_app.command("update")
def agents_update(
    agent_id: str = typer.Argument(..., help="Agent ID (agent_01...)"),
    name: Optional[str] = typer.Option(None, "--name", "-n", help="New agent name"),
    system: Optional[str] = typer.Option(None, "--system", "-s", help="New system prompt"),
    model: Optional[str] = typer.Option(None, "--model", "-m", help="New model"),
    version: Optional[int] = typer.Option(None, "--version", help="Agent version (required by API)"),
):
    """Update an existing agent's name, system prompt, or model.

    Example:
        praisonai managed agents update agent_01AbCdEf --name "New Name" --version 1
        praisonai managed agents update agent_01AbCdEf --system "You are a data analyst." --version 2
    """
    client = _get_client()
    kwargs = {}
    if name:
        kwargs["name"] = name
    if system:
        kwargs["system"] = system
    if model:
        kwargs["model"] = model
    if version is not None:
        kwargs["version"] = version
    if not kwargs:
        typer.echo("Nothing to update. Pass --name, --system, or --model.")
        raise typer.Exit(0)
    updated = client.beta.agents.update(agent_id, **kwargs)
    typer.echo(f"Updated agent: {updated.id} (v{getattr(updated,'version','')})")


@agents_app.command("delete")
def agents_delete(
    agent_id: str = typer.Argument(..., help="Agent ID to delete (agent_01...)"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt"),
):
    """Delete an agent.

    Example:
        praisonai managed agents delete agent_01AbCdEf
        praisonai managed agents delete agent_01AbCdEf --yes
    """
    if not yes:
        confirm = typer.confirm(f"Are you sure you want to delete agent {agent_id}?")
        if not confirm:
            typer.echo("Deletion cancelled.")
            raise typer.Exit(0)

    client = _get_client()
    try:
        client.beta.agents.delete(agent_id)
        typer.echo(f"Agent {agent_id} deleted successfully.")
    except Exception as e:
        typer.echo(f"Error deleting agent: {e}")
        raise typer.Exit(1)


# ─────────────────────────────────────────────────────────────────────────────
# envs sub-commands
# ─────────────────────────────────────────────────────────────────────────────

@envs_app.command("list")
def envs_list(
    limit: int = typer.Option(10, "--limit", "-l", help="Max environments to return"),
):
    """List sandbox environments on your Anthropic account.

    Example:
        praisonai managed envs list
    """
    client = _get_client()
    envs = client.beta.environments.list(limit=limit)
    rows = getattr(envs, "data", envs)
    if not rows:
        typer.echo("No environments found.")
        return
    typer.echo(f"{'ID':<40} {'STATUS':<12} NAME")
    typer.echo("-" * 70)
    for e in rows:
        typer.echo(f"{e.id:<40} {getattr(e,'status',''):<12} {getattr(e,'name','')}")


@envs_app.command("get")
def envs_get(
    env_id: str = typer.Argument(..., help="Environment ID (env_01...)"),
):
    """Get details for a specific environment.

    Example:
        praisonai managed envs get env_01AbCdEf
    """
    client = _get_client()
    e = client.beta.environments.retrieve(env_id)
    typer.echo(f"ID    : {e.id}")
    typer.echo(f"Name  : {getattr(e, 'name', '')}")
    typer.echo(f"Status: {getattr(e, 'status', '')}")
    cfg = getattr(e, "config", None)
    if cfg:
        typer.echo(f"Config: {cfg}")


@envs_app.command("update")
def envs_update(
    env_id: str = typer.Argument(..., help="Environment ID (env_01...)"),
    packages: Optional[str] = typer.Option(None, "--packages", "-p", help="Comma-separated pip packages"),
    networking: Optional[str] = typer.Option(None, "--networking", help="Networking type: 'full' or 'limited'"),
):
    """Update an environment's configuration.

    Example:
        praisonai managed envs update env_01AbCdEf --packages "numpy,pandas"
        praisonai managed envs update env_01AbCdEf --networking limited
    """
    kwargs = {}
    
    if packages:
        pkg_list = [p.strip() for p in packages.split(",") if p.strip()]
        if not pkg_list:
            typer.echo("Error: --packages must include at least one non-empty package name")
            raise typer.Exit(1)
        kwargs["packages"] = {"pip": pkg_list}
    
    if networking:
        networking_lower = networking.lower()
        if networking_lower not in ["full", "limited"]:
            typer.echo("Error: --networking must be 'full' or 'limited'")
            raise typer.Exit(1)
        kwargs["networking"] = {"type": networking_lower}
    
    if not kwargs:
        typer.echo("Nothing to update. Pass --packages or --networking.")
        raise typer.Exit(0)
    
    # Get client only after validation and early-exit checks
    client = _get_client()
    
    try:
        updated = client.beta.environments.update(env_id, **kwargs)
        typer.echo(f"Updated environment: {updated.id}")
    except Exception as e:
        typer.echo(f"Error updating environment: {e}")
        raise typer.Exit(1)


@envs_app.command("delete")
def envs_delete(
    env_id: str = typer.Argument(..., help="Environment ID to delete (env_01...)"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt"),
):
    """Delete an environment.

    Example:
        praisonai managed envs delete env_01AbCdEf
        praisonai managed envs delete env_01AbCdEf --yes
    """
    if not yes:
        confirm = typer.confirm(f"Are you sure you want to delete environment {env_id}?")
        if not confirm:
            typer.echo("Deletion cancelled.")
            raise typer.Exit(0)

    client = _get_client()
    try:
        client.beta.environments.delete(env_id)
        typer.echo(f"Environment {env_id} deleted successfully.")
    except Exception as e:
        typer.echo(f"Error deleting environment: {e}")
        raise typer.Exit(1)


# ─────────────────────────────────────────────────────────────────────────────
# ids sub-commands  (save / restore / show — no Anthropic IDs are user-defined)
# ─────────────────────────────────────────────────────────────────────────────

_DEFAULT_IDS_FILE = pathlib.Path("managed_ids.json")


@ids_app.command("show")
def ids_show(
    file: pathlib.Path = typer.Option(_DEFAULT_IDS_FILE, "--file", "-f", help="IDs file path"),
):
    """Show saved Anthropic-assigned IDs from a JSON file.

    Example:
        praisonai managed ids show
        praisonai managed ids show --file /tmp/my_ids.json
    """
    if not file.exists():
        typer.echo(f"No IDs file found at {file}. Run a prompt first or use 'ids save'.")
        raise typer.Exit(1)
    ids = json.loads(file.read_text())
    typer.echo(f"File: {file}")
    for k, v in ids.items():
        typer.echo(f"  {k:<20}: {v}")


@ids_app.command("save")
def ids_save(
    agent_id: str = typer.Argument(..., help="Agent ID (agent_01...)"),
    environment_id: str = typer.Argument(..., help="Environment ID (env_01...)"),
    session_id: str = typer.Argument(..., help="Session ID (sesn_01...)"),
    agent_version: Optional[int] = typer.Option(None, "--version", help="Agent version"),
    file: pathlib.Path = typer.Option(_DEFAULT_IDS_FILE, "--file", "-f", help="Output file path"),
):
    """Save Anthropic-assigned IDs to a JSON file for later restore.

    Anthropic assigns all IDs — you cannot define your own.
    Use this to persist them so you can skip re-creating resources.

    Example:
        praisonai managed ids save agent_01... env_01... sesn_01... --version 1
    """
    ids = {
        "agent_id": agent_id,
        "agent_version": agent_version,
        "environment_id": environment_id,
        "session_id": session_id,
    }
    file.write_text(json.dumps(ids, indent=2))
    typer.echo(f"Saved IDs to {file}:")
    for k, v in ids.items():
        typer.echo(f"  {k}: {v}")


@ids_app.command("restore")
def ids_restore(
    prompt: str = typer.Argument(..., help="Prompt to send after restoring IDs"),
    file: pathlib.Path = typer.Option(_DEFAULT_IDS_FILE, "--file", "-f", help="IDs file to restore from"),
    stream: bool = typer.Option(True, "--stream/--no-stream", help="Stream response"),
):
    """Restore saved IDs and run a prompt — skips creating agent/env/session.

    Example:
        praisonai managed ids restore "Continue the previous task"
        praisonai managed ids restore "What did we do?" --file /tmp/my_ids.json
    """
    if not file.exists():
        typer.echo(f"No IDs file at {file}. Run 'praisonai managed ids save ...' first.")
        raise typer.Exit(1)

    try:
        from praisonai import Agent, ManagedAgent
    except ImportError:
        typer.echo("Error: pip install praisonai")
        raise typer.Exit(1)

    ids = json.loads(file.read_text())
    typer.echo(f"Restoring IDs from {file}:")
    for k, v in ids.items():
        typer.echo(f"  {k}: {v}")
    typer.echo("")

    managed = ManagedAgent()
    managed.restore_ids(ids)

    agent = Agent(name="managed-agent", backend=managed)
    result = agent.start(prompt, stream=stream)
    if result and not stream:
        print(result)


# ─────────────────────────────────────────────────────────────────────────────
# Register sub-apps onto main app
# ─────────────────────────────────────────────────────────────────────────────
app.add_typer(sessions_app, name="sessions")
app.add_typer(agents_app,   name="agents")
app.add_typer(envs_app,     name="envs")
app.add_typer(ids_app,      name="ids")
