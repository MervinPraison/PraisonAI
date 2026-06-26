"""
Run command group for PraisonAI CLI.

Provides agent execution commands.
"""

from typing import Any, Dict, Optional, List

import typer

from ..output.console import get_output_controller
from ..state.identifiers import get_current_context
from ..configuration.resolver import resolve_config

app = typer.Typer(help="Run agents")


def _parse_permissions(allow: Optional[List[str]], deny: Optional[List[str]], permissions_file: Optional[str], default: Optional[str]) -> Optional[dict]:
    """Parse permission flags into a config dict.
    
    Args:
        allow: Pattern to allow
        deny: Pattern to deny
        permissions_file: Path to permissions file (YAML or JSON)
        default: Default action (allow/deny/ask)
        
    Returns:
        Dict mapping patterns to actions, or None if no permissions specified
    """
    if not any([allow, deny, permissions_file, default]):
        return None
    
    import json
    import yaml
    
    config = {}
    
    # Load from file if provided
    if permissions_file:
        try:
            with open(permissions_file, 'r') as f:
                if permissions_file.endswith('.json'):
                    file_config = json.load(f)
                else:
                    file_config = yaml.safe_load(f)
                if isinstance(file_config, dict):
                    config.update(file_config)
        except (IOError, json.JSONDecodeError, yaml.YAMLError) as e:
            from ..output.console import get_output_controller
            get_output_controller().print_warning(f"Failed to load permissions file: {e}")
    
    # Add CLI patterns (override file config)
    if allow:
        for pattern in allow:
            config[pattern] = "allow"
    if deny:
        for pattern in deny:
            config[pattern] = "deny"
    
    # Add default pattern if specified
    if default and default in ("allow", "deny", "ask"):
        config["*"] = default
    
    return config if config else None


def _mcp_server_to_command(server: dict) -> Optional[tuple]:
    """Convert a resolved MCP server config entry to a (command, env) pair.

    Supports the project ``config.yaml`` schema where a server is declared as
    either ``command: ["npx", "-y", "@playwright/mcp"]`` (list) or
    ``command: "npx -y @playwright/mcp"`` (string), with optional ``args`` and
    ``env`` keys. Remote servers and disabled servers return None.

    Returns:
        Tuple of (command_string, env_string) suitable for ``args.mcp`` /
        ``args.mcp_env``, or None if the server cannot be expressed that way.
    """
    if not isinstance(server, dict):
        return None
    if server.get("enabled") is False:
        return None
    # Only local (stdio) servers map to the command-string CLI path.
    if server.get("type") == "remote" or server.get("url"):
        return None

    command = server.get("command")
    args = server.get("args") or []

    import shlex

    if isinstance(command, list):
        parts = [str(p) for p in command]
    elif isinstance(command, str) and command:
        parts = shlex.split(command)
    else:
        return None

    if args:
        parts = parts + [str(a) for a in args]
    if not parts:
        return None

    # Quote each token so values with spaces/metacharacters survive the
    # downstream ``shlex.split`` in the MCP handler.
    command_str = " ".join(shlex.quote(part) for part in parts)

    env = server.get("env") or {}
    env_str = None
    if isinstance(env, dict) and env:
        # The downstream parser splits env on commas, so a comma inside a value
        # would corrupt it. Skip such entries with a warning rather than
        # silently producing wrong env vars.
        safe_pairs = []
        for k, v in env.items():
            v_str = str(v)
            if "," in v_str:
                import warnings
                warnings.warn(
                    f"MCP env var '{k}' contains a comma and cannot be passed "
                    "via the command-string CLI path; skipping it.",
                    stacklevel=2,
                )
                continue
            safe_pairs.append(f"{k}={v_str}")
        if safe_pairs:
            env_str = ",".join(safe_pairs)

    return command_str, env_str


def _resolve_mcp_from_config(config) -> Optional[tuple]:
    """Pick the first enabled local MCP server from resolved config.

    The CLI ``--mcp`` flag accepts a single server command, so when wiring
    project config we surface the first enabled stdio server.

    Returns:
        Tuple of (command_string, env_string) or None.
    """
    mcp = getattr(config, "mcp", None) or {}
    if not isinstance(mcp, dict):
        return None
    servers = mcp.get("servers") or {}
    if not isinstance(servers, dict):
        return None

    selected = None
    enabled_local = []
    for name, server in servers.items():
        result = _mcp_server_to_command(server)
        if result:
            enabled_local.append(name)
            if selected is None:
                selected = result

    # The CLI command-string path supports a single server. Warn so a user who
    # declared several enabled local servers knows only the first is wired.
    if len(enabled_local) > 1:
        import warnings
        warnings.warn(
            "Multiple enabled local MCP servers found in config "
            f"({', '.join(enabled_local)}); only '{enabled_local[0]}' will be "
            "used via the run command path.",
            stacklevel=2,
        )

    return selected


def _permissions_from_config(config) -> Optional[dict]:
    """Convert a resolved ``permissions`` config section to a pattern->action dict.

    Supports both the rule-list form::

        permissions:
          default: ask
          rules:
            - { pattern: "bash:git *", action: allow }

    and a flat ``pattern: action`` mapping. The flat mapping mirrors the format
    produced by ``_parse_permissions`` (used by ``--allow``/``--deny`` and
    ``--permissions``), so both paths converge on the same structure.
    """
    permissions = getattr(config, "permissions", None) or {}
    if not isinstance(permissions, dict) or not permissions:
        return None

    result: dict = {}

    rules = permissions.get("rules")
    if isinstance(rules, list):
        for rule in rules:
            if isinstance(rule, dict):
                pattern = rule.get("pattern")
                action = rule.get("action")
                if pattern and action in ("allow", "deny", "ask"):
                    result[pattern] = action

    default = permissions.get("default")
    if default in ("allow", "deny", "ask"):
        result["*"] = default

    # Allow a flat pattern->action mapping alongside the structured form.
    for key, value in permissions.items():
        if key in ("rules", "default"):
            continue
        if isinstance(value, str) and value in ("allow", "deny", "ask"):
            result[key] = value

    return result or None


def _apply_config_defaults(
    mcp: Optional[str],
    mcp_env: Optional[str],
    permissions_config: Optional[dict],
) -> tuple:
    """Layer resolved project config under explicit CLI flags.

    MCP servers and permission policy declared in ``.praisonai/config.yaml`` are
    surfaced here so any ``praisonai run`` in the directory inherits them. CLI
    flags always take precedence (they are passed in already-resolved and only
    config-derived values fill the gaps).

    Returns:
        Tuple of (mcp, mcp_env, permissions_config) with config defaults applied.
    """
    try:
        config = resolve_config()
    except (ValueError, OSError):
        return mcp, mcp_env, permissions_config

    # MCP: only fill in if no explicit --mcp flag was given.
    if not mcp:
        resolved_mcp = _resolve_mcp_from_config(config)
        if resolved_mcp:
            mcp, config_env = resolved_mcp
            if not mcp_env and config_env:
                mcp_env = config_env

    # Permissions: merge config rules underneath CLI-provided rules.
    config_perms = _permissions_from_config(config)
    if config_perms:
        if permissions_config:
            merged = dict(config_perms)
            merged.update(permissions_config)  # CLI flags override config
            permissions_config = merged
        else:
            permissions_config = config_perms

    return mcp, mcp_env, permissions_config


def _checkpoints_auto_enabled() -> bool:
    """Whether automatic run-checkpointing is enabled via project config.

    Reads the ``checkpoints.auto`` key from the resolved project config
    (stored under ``extra``). Defaults to ``True`` so interactive terminal
    runs get an automatic safety net; opt out with ``--no-checkpoint`` or
    ``checkpoints: {auto: false}``.
    """
    try:
        config = resolve_config()
    except (ValueError, OSError):
        return True

    checkpoints = (getattr(config, "extra", None) or {}).get("checkpoints")
    if isinstance(checkpoints, dict) and "auto" in checkpoints:
        return bool(checkpoints["auto"])
    return True


def _auto_checkpoint(label: str, *, no_checkpoint: bool, workspace_dir: Optional[str] = None) -> None:
    """Create an automatic checkpoint of the workspace before a run.

    ``workspace_dir`` defaults to the current directory but should be the
    directory of the project being run (e.g. the directory containing a target
    YAML file) so the checkpoint protects the files the run will actually
    touch.

    Best-effort and quiet: any failure (e.g. protected path, no git, no
    changes) is swallowed so a checkpoint problem never blocks the run and the
    auto-checkpoint never leaks into machine-readable run output.
    """
    if no_checkpoint or not _checkpoints_auto_enabled():
        return

    import asyncio
    import os

    output = get_output_controller()
    try:
        from ..features.checkpoints import CheckpointsHandler

        handler = CheckpointsHandler(workspace_dir=workspace_dir or os.getcwd())
        asyncio.run(handler.save(label, allow_empty=False, quiet=True))
    except Exception as e:  # pragma: no cover - defensive, never block the run
        if getattr(output, "is_verbose", False):
            output.print_info(f"Auto-checkpoint skipped: {e}")


def _restore_checkpoint(ref: str, workspace_dir: Optional[str] = None) -> None:
    """Restore the workspace to a checkpoint reference ('last' or an id)."""
    import asyncio
    import os

    from ..features.checkpoints import CheckpointsHandler

    handler = CheckpointsHandler(workspace_dir=workspace_dir or os.getcwd())

    async def _run() -> bool:
        service = await handler._get_service()
        checkpoints = await service.list_checkpoints(limit=100)
        if not checkpoints:
            handler._print_error("No checkpoints found to restore")
            return False
        if ref in ("last", "latest"):
            target = checkpoints[0].id
        else:
            # Exact id/short_id first, then a unique prefix; reject ambiguous
            # prefixes so we never restore the wrong workspace.
            exact = [cp.id for cp in checkpoints if cp.id == ref or cp.short_id == ref]
            if exact:
                target = exact[0]
            else:
                prefix_matches = [cp.id for cp in checkpoints if cp.id.startswith(ref)]
                if len(prefix_matches) == 1:
                    target = prefix_matches[0]
                elif len(prefix_matches) > 1:
                    handler._print_error(f"Ambiguous checkpoint reference: {ref}")
                    return False
                else:
                    handler._print_error(f"No checkpoint found for: {ref}")
                    return False
        return await handler.restore(target)

    if not asyncio.run(_run()):
        raise typer.Exit(1)


def _try_attach_runtime(
    prompt: str,
    *,
    model: Optional[str],
    output_mode: Optional[str],
    session_id: Optional[str],
) -> bool:
    """Forward a plain prompt to a warm runtime when one is running.

    Returns True when the request was handled by the warm runtime (so the caller
    should skip in-process execution), or False to fall back to the normal
    in-process path. Any runtime error is treated as a transparent fall-back.

    Only the simple text path is attached: structured ``actions``/``json`` output
    modes and session continuity stay in-process to preserve their behaviour.
    """
    # Structured output modes have richer in-process event bridging; don't attach.
    if output_mode in ("actions", "json", "stream", "stream-json"):
        return False

    try:
        from ...runtime import get_runtime_descriptor, RuntimeClient, RuntimeUnavailable
    except ImportError:
        return False

    descriptor = get_runtime_descriptor()
    if descriptor is None:
        return False

    output = get_output_controller()
    try:
        client = RuntimeClient(descriptor)
        result = client.run(prompt, model=model, session_id=session_id)
    except RuntimeUnavailable:
        # Runtime went away mid-flight; fall back to in-process execution.
        return False

    output.emit_result(
        message="Prompt completed",
        data={"result": str(result) if result else None},
    )
    if result and not output.is_json_mode:
        print(result)
    return True


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
    # Permission flags for CI-safe declarative policies
    allow: Optional[List[str]] = typer.Option(None, "--allow", help="Permission pattern to allow (e.g., 'read:*', 'bash:git *'). Can be repeated."),
    deny: Optional[List[str]] = typer.Option(None, "--deny", help="Permission pattern to deny (e.g., 'bash:rm *'). Can be repeated."),
    permissions: Optional[str] = typer.Option(None, "--permissions", help="Permission file path (YAML or JSON) with allow/deny rules"),
    permission_default: Optional[str] = typer.Option(None, "--permission-default", help="Default action for unmatched patterns: allow, deny, ask (default: ask)"),
    # Session continuity options
    continue_session: bool = typer.Option(False, "--continue", "-c", help="Continue the most recent session for this project"),
    session: Optional[str] = typer.Option(None, "--session", "-s", help="Resume a specific session ID"),
    fork: bool = typer.Option(False, "--fork", help="Fork from the specified session (requires --session)"),
    no_save: bool = typer.Option(False, "--no-save", help="Don't auto-save session after execution"),
    # Custom definitions
    agent: Optional[str] = typer.Option(None, "--agent", "-a", help="Use a named custom agent"),
    command: Optional[str] = typer.Option(None, "--command", help="Execute a named custom command"),
    # Checkpoint / rewind
    no_checkpoint: bool = typer.Option(False, "--no-checkpoint", help="Disable automatic file checkpoint before the run"),
    restore: Optional[str] = typer.Option(None, "--restore", help="Restore the workspace to a checkpoint id (or 'last') and exit"),
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

    # Rewind: restore the workspace to a prior checkpoint and exit. Handled
    # before any execution so `praisonai run --restore last` is a pure undo.
    if restore:
        _restore_checkpoint(restore)
        return

    # Early credential check before any processing
    if target:  # Only check if we actually have something to run
        from ...llm.credentials import is_configured
        import sys
        
        # Check if credentials are configured (use model if provided, else check general)
        if not is_configured(model):
            # In non-interactive mode, show clear error
            if not sys.stdin.isatty() or output.is_json_mode:
                output.print_error(
                    "No API key configured. Run: praisonai setup\n"
                    "or set environment variables like OPENAI_API_KEY"
                )
                raise typer.Exit(1)
            
            # In interactive mode, offer to run setup
            typer.echo(f"No API key configured{f' for model {model}' if model else ''}.")
            run_setup = typer.confirm("Would you like to run the setup wizard now?")
            
            if run_setup:
                from ..commands.setup import _run_setup
                exit_code = _run_setup(
                    non_interactive=False,
                    provider=None,
                    api_key=None,
                    model=None
                )
                if exit_code != 0:
                    output.print_error("Setup failed. Exiting.")
                    raise typer.Exit(exit_code)
                
                output.print_success("Setup complete! Continuing with your run...")
                # Re-check after setup
                if not is_configured(model):
                    output.print_error("Setup completed but credentials still not detected.")
                    raise typer.Exit(1)
            else:
                output.print_info(
                    "To configure credentials:\n"
                    "  - Run: praisonai setup\n"
                    "  - Or set environment variables like OPENAI_API_KEY"
                )
                raise typer.Exit(0)
    
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
        
        # Invocation-level permission flags override per-agent definition.
        invocation_permissions = _parse_permissions(allow, deny, permissions, permission_default)

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
            approval=approval,
            approve_all_tools=approve_all_tools,
            approval_timeout=approval_timeout,
            invocation_permissions=invocation_permissions,
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
        permissions_config = _parse_permissions(allow, deny, permissions, permission_default)
        mcp_command, mcp_env, permissions_config = _apply_config_defaults(
            None, None, permissions_config
        )
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
            permissions_config=permissions_config,
            mcp=mcp_command,
            mcp_env=mcp_env,
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
    from ..output.event_bridge import SCHEMA_VERSION
    output.emit_start(
        message=f"Starting run: {target[:50]}..." if len(target) > 50 else f"Starting run: {target}",
        data={
            "schema_version": SCHEMA_VERSION,
            "target": target,
            "model": model,
            "framework": framework,
        }
    )
    
    # Check if target is a file or prompt
    import os
    is_file = os.path.exists(target) and (target.endswith('.yaml') or target.endswith('.yml'))

    # Auto-checkpoint before file-based runs so a bad turn can be rewound with
    # `praisonai run --restore last`. Scoped to YAML-file runs (which mutate
    # project files) and snapshotted against the file's own directory so the
    # checkpoint protects the right workspace. Plain-prompt runs don't touch
    # project files, so they skip checkpointing (avoiding spurious "no changes"
    # noise). Best-effort and gated by config (`checkpoints.auto`, default on)
    # and `--no-checkpoint`.
    if is_file:
        from ..state.identifiers import get_current_context as _get_ctx
        _run_id = getattr(_get_ctx(), "run_id", None)
        _auto_checkpoint(
            f"run:{_run_id}" if _run_id else "auto checkpoint before run",
            no_checkpoint=no_checkpoint,
            workspace_dir=os.path.dirname(os.path.abspath(target)) or None,
        )
    
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
        permissions_config = _parse_permissions(allow, deny, permissions, permission_default)
        mcp_command, mcp_env, permissions_config = _apply_config_defaults(
            None, None, permissions_config
        )
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
            permissions_config=permissions_config,
            mcp=mcp_command,
            mcp_env=mcp_env,
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
    
    # Note: Credential check already done in run_main() entry point
    
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
            from ..state.project_sessions import find_last_session, session_exists_anywhere
            
            if continue_session:
                # Find last session for this project
                session_id = find_last_session()
                if session_id:
                    output.print_info(f"Continuing session: {session_id}")
                else:
                    output.print_warning("No previous sessions found. Starting new session.")
                    
            elif session:
                # Use specific session
                if session_exists_anywhere(session):
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
    permissions_config: Optional[dict] = None,
    mcp: Optional[str] = None,
    mcp_env: Optional[str] = None,
    continue_session: bool = False,
    session: Optional[str] = None,
    fork: bool = False,
    no_save: bool = False,
):
    """Run a direct prompt."""
    output = get_output_controller()
    
    # Note: Credential check already done in run_main() entry point
    
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
            from ..state.project_sessions import find_last_session, session_exists_anywhere
            
            if continue_session:
                # Find last session for this project
                session_id = find_last_session()
                if session_id:
                    output.print_info(f"Continuing session: {session_id}")
                else:
                    output.print_warning("No previous sessions found. Starting new session.")
                    
            elif session:
                # Use specific session
                if session_exists_anywhere(session):
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

        # Detect-and-attach: if a warm runtime is running, forward the plain
        # prompt to it (skipping per-invocation cold-start) and fall back to
        # in-process execution otherwise. Only the simple text path attaches;
        # per-invocation tool/approval/memory overrides stay in-process so their
        # behaviour is preserved exactly.
        # Session continuity/forking is handled in-process; the warm runtime does
        # not carry session state, so any explicit session flag stays local.
        runtime_eligible = not any([
            mcp, tools, toolset, approval, approve_all_tools,
            memory, permissions_config, continue_session, session, fork,
        ])
        if runtime_eligible and _try_attach_runtime(
            prompt,
            model=model,
            output_mode=output_mode,
            session_id=session_id,
        ):
            return

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
                    permissions_config=permissions_config,
                )
            
            # Add session support to Agent if needed
            from ..utils.project import build_cli_memory_config, apply_cli_session_continuity
            memory_cfg = build_cli_memory_config(session_id=session_id, auto_save=auto_save_name)
            if memory_cfg is not None:
                agent_config["memory"] = memory_cfg
            
            agent = Agent(**agent_config)
            if session_id or auto_save_name:
                apply_cli_session_continuity(agent, session_id or auto_save_name, auto_save=auto_save_name)

            # Bridge per-step agent events into the structured output stream
            # so `--output stream-json` surfaces tool/text events, not just
            # start/result. No-op in non-JSON modes.
            from ..output.event_bridge import attach_bridge, detach_bridge
            bridge = attach_bridge(agent, output)
            if bridge is not None:
                bridge.emit_agent_message(agent_config.get("name"))
            try:
                result = agent.start(prompt)
            finally:
                detach_bridge(agent, bridge)

            if bridge is not None:
                bridge.emit_run_result(result, ok=True)
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
        args.mcp = mcp
        args.mcp_env = mcp_env
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
    
    except typer.Exit:
        raise
    except Exception as e:
        from ..output.event_bridge import StreamEventBridge
        StreamEventBridge(output).emit_run_error(str(e))
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
    
    # Apply session continuity if requested
    session_id = None
    auto_save_name = None
    
    if continue_session or session or fork:
        from ..state.project_sessions import find_last_session, session_exists_anywhere
        
        if continue_session:
            session_id = find_last_session()
            if not session_id:
                typer.echo("Warning: No previous sessions found. Starting new session.", err=True)
        elif session:
            if session_exists_anywhere(session):
                session_id = session
                
                if fork:
                    from praisonaiagents.session.hierarchy import HierarchicalSessionStore
                    from ..utils.project import get_project_sessions_dir
                    
                    hierarchical_store = HierarchicalSessionStore(str(get_project_sessions_dir()))
                    forked_session_id = hierarchical_store.fork_session(session_id)
                    session_id = forked_session_id
            else:
                typer.echo(f"Error: Session not found: {session}", err=True)
                raise typer.Exit(1)
    
    if not no_save:
        import uuid
        auto_save_name = session_id or "session-" + str(uuid.uuid4())[:8]
    if session_id or auto_save_name:
        class Args:
            pass
        
        args = Args()
        args.auto_save = auto_save_name
        args.resume_session = session_id
        args.cli_project_sessions = bool(session_id or auto_save_name)
        
        praison.args = args
    
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
    approval: Optional[str] = None,
    approve_all_tools: bool = False,
    approval_timeout: Optional[str] = None,
    invocation_permissions: Optional[dict] = None,
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
        
        # Resolve per-agent permissions (from definition) layered with
        # invocation flags. Precedence: invocation flags > agent definition.
        agent_permissions = agent_config.pop("permissions", None) or {}
        merged_permissions = dict(agent_permissions)
        if invocation_permissions:
            merged_permissions.update(invocation_permissions)
        
        if merged_permissions:
            from praisonai.cli.features.approval import resolve_approval_config
            # Preserve promptable `ask` rules: only fall back to non-interactive
            # when there is no interactive approval path. An explicit --approval
            # flag or any `ask` rule keeps the backend interactive so the user
            # can be prompted (e.g. the `review` preset's "ask before shell").
            has_ask_rules = any(
                str(action).strip().lower() == "ask"
                for action in merged_permissions.values()
            )
            # Default to a console backend so deny/ask rules are enforced even
            # when no explicit --approval flag is passed.
            agent_config["approval"] = resolve_approval_config(
                approval or "console",
                all_tools=approve_all_tools,
                timeout=approval_timeout,
                non_interactive=approval is None and not has_ask_rules,
                permissions_config=merged_permissions,
            )
        elif approval:
            from praisonai.cli.features.approval import resolve_approval_config
            agent_config["approval"] = resolve_approval_config(
                approval,
                all_tools=approve_all_tools,
                timeout=approval_timeout,
            )
        
        # Handle session continuity
        session_id = None
        auto_save_name = None
        
        if continue_session or session or fork:
            from ..state.project_sessions import find_last_session, session_exists_anywhere
            
            if continue_session:
                session_id = find_last_session()
                if session_id:
                    output.print_info(f"Continuing session: {session_id}")
                else:
                    output.print_warning("No previous sessions found. Starting new session.")
                    
            elif session:
                if session_exists_anywhere(session):
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

        # Bridge per-step agent events into the structured output stream.
        from ..output.event_bridge import attach_bridge, detach_bridge
        bridge = attach_bridge(agent, output)
        if bridge is not None:
            bridge.emit_agent_message(agent_config.get("name"))
        try:
            result = agent.start(prompt)
        finally:
            detach_bridge(agent, bridge)

        if bridge is not None:
            bridge.emit_run_result(result, ok=True)
        output.emit_result(
            message="Agent completed",
            data={"result": str(result) if result else None}
        )
        
        if result and not output.is_json_mode:
            print(result)
    
    except typer.Exit:
        raise
    except Exception as e:
        from ..output.event_bridge import StreamEventBridge
        StreamEventBridge(output).emit_run_error(str(e))
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
    
    # Apply session continuity if requested
    session_id = None
    auto_save_name = None
    
    if continue_session or session or fork:
        from ..state.project_sessions import find_last_session, session_exists_anywhere
        
        if continue_session:
            session_id = find_last_session()
            if not session_id:
                typer.echo("Warning: No previous sessions found. Starting new session.", err=True)
        elif session:
            if session_exists_anywhere(session):
                session_id = session
                
                if fork:
                    from praisonaiagents.session.hierarchy import HierarchicalSessionStore
                    from ..utils.project import get_project_sessions_dir
                    
                    hierarchical_store = HierarchicalSessionStore(str(get_project_sessions_dir()))
                    forked_session_id = hierarchical_store.fork_session(session_id)
                    session_id = forked_session_id
            else:
                typer.echo(f"Error: Session not found: {session}", err=True)
                raise typer.Exit(1)
    
    if not no_save:
        import uuid
        auto_save_name = session_id or "session-" + str(uuid.uuid4())[:8]
    if session_id or auto_save_name:
        from ..state.project_sessions import build_cli_memory_config, apply_cli_session_continuity
        
        memory_cfg = build_cli_memory_config(session_id, auto_save_name)
        if memory_cfg is not None:
            agent_config["memory"] = memory_cfg
    
    agent = Agent(**agent_config)
    if session_id or auto_save_name:
        apply_cli_session_continuity(agent, session_id or auto_save_name, auto_save=auto_save_name)
    
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
