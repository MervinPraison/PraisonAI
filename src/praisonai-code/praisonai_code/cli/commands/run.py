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


_FRAMEWORK_HELP = "Framework: praisonai, crewai, autogen"


def _is_yaml_file(target: Optional[str]) -> bool:
    """Return True when ``target`` is an existing YAML file path.

    Case-insensitive on the extension so uppercase paths (e.g. ``AGENTS.YAML``)
    are recognised as file targets. Shared by the stdin-ingestion gate and the
    downstream file/prompt routing so both decisions stay in lockstep.
    """
    import os
    return bool(
        target
        and os.path.exists(target)
        and target.lower().endswith((".yaml", ".yml"))
    )


# Structured output modes always run in-process via the Agent path, so they
# never need the wrapper's handle_direct_prompt.
_IN_PROCESS_OUTPUT_MODES = ("actions", "json", "stream", "stream-json")


def _direct_prompt_needs_wrapper(
    target: Optional[str],
    *,
    agent: Optional[str],
    command: Optional[str],
    output_mode: Optional[str],
) -> bool:
    """True when a text prompt run uses the wrapper-only handle_direct_prompt path.

    Structured modes (``_IN_PROCESS_OUTPUT_MODES``) always run in-process via the
    Agent path, so they never need the wrapper. Human-readable text modes
    (``plain``/``verbose``/``silent``/default) delegate to the wrapper's
    ``handle_direct_prompt``; on a standalone install this gates with an install
    hint (see ``_require_wrapper_for_default_run``) to keep the C7 hot path free
    of the heavy Agent import for default runs.
    """
    if agent or command or not target or _is_yaml_file(target):
        return False
    return output_mode not in _IN_PROCESS_OUTPUT_MODES


def _require_wrapper_for_default_run(
    target: Optional[str],
    *,
    agent: Optional[str],
    command: Optional[str],
    output_mode: Optional[str],
) -> None:
    """Fail fast with an install hint before credential/setup checks.

    Human-readable text runs (default/plain/verbose/silent) delegate to the
    wrapper's ``handle_direct_prompt``. On a standalone install the wrapper is
    absent, so gate here with an install hint that points standalone users to
    the in-process ``--output actions`` alternative.
    """
    if not _direct_prompt_needs_wrapper(
        target, agent=agent, command=command, output_mode=output_mode
    ):
        return
    from praisonai_code._wrapper_bridge import wrapper_available

    if wrapper_available():
        return
    output = get_output_controller()
    output.print_error(
        "Default run mode requires the praisonai wrapper. "
        "Install with: pip install praisonai\n"
        "Standalone alternative: praisonai-code run --output actions \"your prompt\""
    )
    raise typer.Exit(1)


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


def _collect_mcp_servers_from_config(config) -> List[dict]:
    """Collect all enabled MCP servers from resolved config.

    Returns a list of normalized server dicts (both local stdio and remote
    URL servers). The structured list is handed to the core MCP client, which
    already supports stdio, SSE, HTTP-stream and websocket transports — so a
    project that declares multiple and/or remote servers gets every enabled
    one wired, not just the first stdio one.

    Returns:
        List of server config dicts (possibly empty).
    """
    mcp = getattr(config, "mcp", None) or {}
    if not isinstance(mcp, dict):
        return []
    servers = mcp.get("servers") or {}
    if not isinstance(servers, dict):
        return []

    collected: List[dict] = []
    for name, server in servers.items():
        if not isinstance(server, dict):
            continue
        if server.get("enabled") is False:
            continue
        entry = dict(server)
        entry.setdefault("name", name)
        collected.append(entry)
    return collected


def _build_mcp_tools(
    mcp: Optional[str],
    mcp_env: Optional[str],
    mcp_servers: Optional[List[dict]],
    verbose: bool = False,
) -> list:
    """Build aggregated MCP tools from a command string and/or structured list.

    Both the single ``--mcp`` command string (ad-hoc) and every enabled server
    from project config (local stdio *and* remote/URL) are wired, so the run
    path exposes all configured MCP servers to the agent — not just the first.

    Returns:
        A flat list of MCP tool callables (possibly empty).
    """
    tools: list = []
    try:
        from praisonai_code.cli.features.mcp import MCPHandler
    except ImportError:
        return tools

    handler = MCPHandler(verbose=verbose)

    if mcp:
        mcp_instance = handler.create_mcp_tools(mcp, mcp_env)
        if mcp_instance:
            tools.extend(list(mcp_instance))

    for server in mcp_servers or []:
        mcp_instance = handler.create_mcp_from_server(server)
        if mcp_instance:
            tools.extend(list(mcp_instance))

    return tools


def _resolve_tools_arg(value: Optional[str], verbose: bool = False) -> list:
    """Resolve a ``--tools`` value into a list of tool callables.

    ``value`` may be a comma-separated list of tool *names* (resolved by name
    through :class:`ToolResolver`, so CLI == YAML == Python), a path to a
    ``tools.py`` file, or a mix of both. Items ending in ``.py`` or that exist
    on disk are loaded as files; everything else is resolved by name.

    Returns an empty list when ``value`` is falsy so callers can unconditionally
    extend an agent's tool list.
    """
    import os as _os

    if not value:
        return []

    from praisonai_code.tool_resolver import ToolResolver
    resolver = ToolResolver()
    resolved: list = []
    for item in (v.strip() for v in value.split(",")):
        if not item:
            continue
        if item.endswith(".py") or _os.path.exists(item):
            module_fns = resolver.load_functions_from_module(item)
            if module_fns:
                resolved.extend(module_fns.values())
            elif not _os.path.exists(item):
                # A .py name that isn't on disk: fall through to name resolution.
                # Strip the .py suffix so "internet_search.py" resolves as the
                # named tool "internet_search" instead of missing outright.
                name_only = item[:-3] if item.endswith(".py") else item
                tool = resolver.resolve(name_only, instantiate=True)
                if tool is not None:
                    resolved.append(tool)
                else:
                    from ..output import get_output_controller
                    get_output_controller().print_info(
                        f"Unknown tool '{item}'. Run 'praisonai tools list' to see available tools."
                    )
            else:
                # tools.py present on disk but produced no callables.
                from ..output import get_output_controller
                if not _os.environ.get("PRAISONAI_ALLOW_LOCAL_TOOLS"):
                    get_output_controller().print_info(
                        f"Skipped '{item}': set PRAISONAI_ALLOW_LOCAL_TOOLS=true to load local tools."
                    )
                else:
                    get_output_controller().print_info(
                        f"No callable tools found in '{item}'."
                    )
        else:
            tool = resolver.resolve(item, instantiate=True)
            if tool is not None:
                resolved.append(tool)
            else:
                from ..output import get_output_controller
                get_output_controller().print_info(
                    f"Unknown tool '{item}'. Run 'praisonai tools list' to see available tools."
                )
    return resolved


def _auto_discover_project_tools(existing: list, verbose: bool = False) -> list:
    """Return auto-discovered ``.praisonai/tools/*.py`` callables to append.

    Mirrors the agents/commands convention: project-local tools are loaded from
    ``.praisonai/tools/`` (user-global + project walk-up) with no ``--tools``
    flag. Loading executes user code and is gated by the shared
    ``PRAISONAI_ALLOW_LOCAL_TOOLS`` opt-in, so this returns an empty list when
    the opt-in is not set.

    Discovery is additive: explicit ``--tools`` items already in ``existing``
    take precedence and are not re-added (dedup by callable identity).
    """
    try:
        from praisonai_code.cli.features.custom_definitions import (
            discover_project_tools,
        )
    except Exception:
        return []

    try:
        discovered = discover_project_tools()
    except Exception:
        return []

    if not discovered:
        return []

    seen = {id(t) for t in existing}
    merged: list = []
    for tool in discovered:
        if id(tool) in seen:
            continue
        seen.add(id(tool))
        merged.append(tool)

    if merged and verbose:
        from ..output import get_output_controller
        get_output_controller().print_info(
            f"Loaded {len(merged)} project tool(s) from .praisonai/tools/"
        )
    return merged


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

    All enabled MCP servers from config — multiple local stdio servers *and*
    remote/URL servers — are collected into a structured list so the run path
    can wire every one of them, not just the first stdio server.

    Returns:
        Tuple of (mcp, mcp_env, permissions_config, mcp_servers) with config
        defaults applied. ``mcp_servers`` is a (possibly empty) list of
        structured server config dicts.
    """
    mcp_servers: List[dict] = []
    try:
        config = resolve_config()
    except (ValueError, OSError):
        return mcp, mcp_env, permissions_config, mcp_servers

    # MCP: collect all enabled servers (local + remote) from config. The
    # explicit single-string ``--mcp`` flag, when given, is wired separately
    # via ``args.mcp`` and merged alongside these by the run handler.
    mcp_servers = _collect_mcp_servers_from_config(config)

    # Permissions: merge config rules underneath CLI-provided rules.
    config_perms = _permissions_from_config(config)
    if config_perms:
        if permissions_config:
            merged = dict(config_perms)
            merged.update(permissions_config)  # CLI flags override config
            permissions_config = merged
        else:
            permissions_config = config_perms

    return mcp, mcp_env, permissions_config, mcp_servers


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


def _checkpoints_storage_dir() -> Optional[str]:
    """Return a configured ``checkpoints.storage_dir`` (or ``None``).

    Keeps ``praisonai run`` auto-checkpoints and restores reading from the same
    store the rest of the CLI (``code --checkpoints``, ``praisonai checkpoint``)
    uses when ``checkpoints.storage_dir`` is configured.
    """
    try:
        config = resolve_config()
    except (ValueError, OSError):
        return None
    checkpoints = (getattr(config, "extra", None) or {}).get("checkpoints")
    if isinstance(checkpoints, dict):
        return checkpoints.get("storage_dir")
    return None


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
        from praisonai_code.cli.features.checkpoints import CheckpointsHandler

        handler = CheckpointsHandler(
            workspace_dir=workspace_dir or os.getcwd(),
            storage_dir=_checkpoints_storage_dir(),
        )
        asyncio.run(handler.save(label, allow_empty=False, quiet=True))
    except Exception as e:  # pragma: no cover - defensive, never block the run
        if getattr(output, "is_verbose", False):
            output.print_info(f"Auto-checkpoint skipped: {e}")


def _restore_checkpoint(ref: str, workspace_dir: Optional[str] = None) -> None:
    """Restore the workspace to a checkpoint reference ('last' or an id)."""
    import asyncio
    import os

    from praisonai_code.cli.features.checkpoints import CheckpointsHandler

    handler = CheckpointsHandler(
        workspace_dir=workspace_dir or os.getcwd(),
        storage_dir=_checkpoints_storage_dir(),
    )

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
        from praisonai_code.runtime import get_runtime_descriptor, RuntimeClient, RuntimeUnavailable
    except ImportError:
        return False

    # Require a version-compatible runtime: a stale (major-mismatched) server is
    # not attached to, so the cold in-process path runs instead of silently
    # talking to an incompatible runtime.
    descriptor = get_runtime_descriptor(require_compatible=True)
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
    framework: Optional[str] = typer.Option(None, "--framework", "-f", help=_FRAMEWORK_HELP),
    interactive: bool = typer.Option(False, "--interactive", "-i", help="Interactive mode"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output"),
    stream: bool = typer.Option(False, "--stream/--no-stream", help="Stream output (default: off for production use)"),
    trace: bool = typer.Option(False, "--trace", help="Enable tracing"),
    memory: bool = typer.Option(False, "--memory", help="Enable memory"),
    tools: Optional[str] = typer.Option(None, "--tools", "-t", help="Comma-separated tool names (e.g. web_search,github) or a tools.py file path"),
    toolset: Optional[str] = typer.Option(None, "--toolset", help="Named toolset groups (comma-separated, e.g., web,files)"),
    max_tokens: int = typer.Option(16000, "--max-tokens", help="Maximum output tokens"),
    profile: bool = typer.Option(False, "--profile", help="Enable CLI profiling (timing breakdown)"),
    profile_deep: bool = typer.Option(False, "--profile-deep", help="Enable deep profiling (cProfile stats, higher overhead)"),
    output_mode: Optional[str] = typer.Option(None, "--output", "-o", help="Output mode: silent (default), actions, verbose, json, stream"),
    approval: Optional[str] = typer.Option(None, "--approval", help="Approval backend: console, plan, accept-edits, bypass, auto, agent, none, slack, telegram, discord, webhook, http, secure, presentation"),
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
    subagents: Optional[str] = typer.Option(None, "--subagents", help="Comma-separated named agents (.praisonai/agents/*.md) the running agent may delegate to. Omit to expose agents marked 'mode: subagent'."),
    command: Optional[str] = typer.Option(None, "--command", help="Execute a named custom command"),
    # Reasoning effort
    thinking: Optional[str] = typer.Option(None, "--thinking", help="Reasoning effort (off, minimal, low, medium, high)"),
    # Checkpoint / rewind
    no_checkpoint: bool = typer.Option(False, "--no-checkpoint", help="Disable automatic file checkpoint before the run"),
    restore: Optional[str] = typer.Option(None, "--restore", help="Restore the workspace to a checkpoint id (or 'last') and exit"),
    # Warm-runtime live session: tag this run so other terminals can `attach`.
    attach: Optional[str] = typer.Option(None, "--attach", help="Run on the warm runtime under this session id so other terminals can observe it via `praisonai attach <id>`"),
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
    # before any execution (and before stdin ingestion) so `praisonai run
    # --restore last` is a pure undo that never drains a pipe it won't use.
    if restore:
        _restore_checkpoint(restore)
        return

    # Ingest piped stdin so `run` composes in Unix pipelines and CI, e.g.
    #   cat error.log | praisonai run "Diagnose the root cause"
    # The prompt argument comes first, then the piped body. Non-blocking/EOF-safe
    # so an interactive TTY is never stalled; isatty()-based mode detection below
    # is preserved. Skipped for file/agent/command flows where merging a piped
    # body into a YAML path or named definition would be meaningless.
    if not (agent or command) and not _is_yaml_file(target):
        from ..utils.stdin import resolve_cli_input
        target = resolve_cli_input(target)

    # Validate --thinking and resolve it to the core thinking_budget up front so
    # an unknown value fails closed before any execution (consistent with the
    # `code` command and MODE_RULES validation on custom agents).
    from praisonai_code.cli.features.thinking import thinking_to_budget
    try:
        thinking_budget = thinking_to_budget(thinking)
    except ValueError as exc:
        output.print_error(str(exc))
        raise typer.Exit(1)

    _require_wrapper_for_default_run(
        target, agent=agent, command=command, output_mode=output_mode
    )

    # Early credential check before any processing
    if target:  # Only check if we actually have something to run
        from praisonai_code.llm.credentials import (
            inject_credentials_into_env,
            is_configured,
        )
        import sys
        
        # Check if credentials are configured (use model if provided, else check general)
        inject_credentials_into_env()
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
                from praisonai_code.cli.commands.setup import _run_setup
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
                inject_credentials_into_env()
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

    # --attach tags a warm-runtime run so other terminals can observe it, but
    # only the direct-prompt path forwards to the warm runtime. Reject it up
    # front on profile/custom-agent/custom-command flows so users never
    # pass --attach and silently get a session that produces no events.
    if attach and (agent or command or profile or profile_deep):
        output.print_error("--attach is only supported for direct prompt runs")
        raise typer.Exit(1)

    # Handle custom agent or command
    if agent:
        from praisonai_code.cli.features.custom_definitions import load_agent_from_name
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
            thinking_budget=thinking_budget,
            subagents=subagents,
        )
        return
    
    if command:
        from praisonai_code.cli.features.custom_definitions import (
            ShellSubstitutionError,
            interpolate_command_template,
        )
        try:
            prompt = interpolate_command_template(command, target or "")
        except ShellSubstitutionError as exc:
            output.print_error(str(exc))
            raise typer.Exit(1)
        if not prompt:
            output.print_error(f"Command '{command}' not found")
            raise typer.Exit(1)
        
        # Run the interpolated command as a prompt
        permissions_config = _parse_permissions(allow, deny, permissions, permission_default)
        mcp_command, mcp_env, permissions_config, mcp_servers = _apply_config_defaults(
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
            mcp_servers=mcp_servers,
            continue_session=continue_session,
            session=session,
            fork=fork,
            no_save=no_save,
            thinking_budget=thinking_budget,
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
            f"  --framework, -f   {_FRAMEWORK_HELP}\n"
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
    
    # Check if target is a file or prompt (case-insensitive extension, shared
    # with the stdin-ingestion gate above so both decisions stay consistent).
    is_file = _is_yaml_file(target)

    # Only the direct-prompt path forwards to the warm runtime, so reject
    # --attach on file execution rather than letting it run with no observable
    # session (the attach client would wait forever for events).
    if attach and is_file:
        output.print_error("--attach is only supported for direct prompt runs")
        raise typer.Exit(1)

    # Auto-checkpoint before file-based runs so a bad turn can be rewound with
    # `praisonai run --restore last`. Scoped to YAML-file runs (which mutate
    # project files) and snapshotted against the file's own directory so the
    # checkpoint protects the right workspace. Plain-prompt runs don't touch
    # project files, so they skip checkpointing (avoiding spurious "no changes"
    # noise). Best-effort and gated by config (`checkpoints.auto`, default on)
    # and `--no-checkpoint`.
    if is_file:
        import os
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
        mcp_command, mcp_env, permissions_config, mcp_servers = _apply_config_defaults(
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
            mcp_servers=mcp_servers,
            continue_session=continue_session,
            session=session,
            fork=fork,
            no_save=no_save,
            attach_session=attach,
            thinking_budget=thinking_budget,
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
        from praisonai_code.cli.main import PraisonAI
        
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
        
        _record_session_usage(session_id or auto_save_name, model, output)
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
    mcp_servers: Optional[List[dict]] = None,
    continue_session: bool = False,
    session: Optional[str] = None,
    fork: bool = False,
    no_save: bool = False,
    attach_session: Optional[str] = None,
    thinking_budget: Optional[int] = None,
):
    """Run a direct prompt."""
    output = get_output_controller()
    
    # Note: Credential check already done in run_main() entry point
    
    try:
        # Handle session continuity first (before any execution mode)
        from praisonai_code.cli.main import PraisonAI
        
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
        # Default auto-save also stays in-process until the warm path can persist
        # sessions the same way as the normal run path.
        # An explicit --thinking budget is a per-invocation override (like tools/
        # approval/memory), so it stays in-process: the warm runtime reuses a
        # cached agent and does not carry a per-call thinking budget, so attaching
        # would silently drop the requested setting.
        runtime_eligible = no_save and thinking_budget is None and not any([
            mcp, mcp_servers, tools, toolset, approval, approve_all_tools,
            memory, permissions_config, continue_session, session, fork,
        ])
        # When --attach <id> is given, tag the warm-runtime run with that id so
        # other terminals (`praisonai attach <id>`) observe its live events.
        runtime_session_id = attach_session or session_id
        if runtime_eligible and _try_attach_runtime(
            prompt,
            model=model,
            output_mode=output_mode,
            session_id=runtime_session_id,
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
                from praisonai_code.cli.features._approval_bridge import resolve_approval_config
                agent_config["approval"] = resolve_approval_config(
                    approval, all_tools=approve_all_tools, timeout=approval_timeout,
                    permissions_config=permissions_config,
                )
            
            # Add session support to Agent if needed
            # NOTE: build_cli_memory_config / apply_cli_session_continuity are
            # imported above from ..state.project_sessions. Do NOT re-import them
            # from ..utils.project here — that stale version lacks the auto_save
            # kwarg and would shadow the correct implementation.
            memory_cfg = build_cli_memory_config(session_id=session_id, auto_save=auto_save_name)
            if memory_cfg is not None:
                agent_config["memory"] = memory_cfg

            # Wire all configured MCP servers (ad-hoc --mcp + config local/remote).
            if mcp or mcp_servers:
                mcp_tools = _build_mcp_tools(mcp, mcp_env, mcp_servers, verbose=verbose)
                if mcp_tools:
                    agent_config["tools"] = list(agent_config.get("tools", [])) + mcp_tools

            # Wire --tools (names or file) and --toolset so actions mode reaches
            # parity with the default/YAML/Python surfaces (previously dropped).
            selected_tools = _resolve_tools_arg(tools, verbose=verbose)
            if toolset:
                from praisonai_code.tool_resolver import resolve_toolsets as _resolve_toolsets
                toolset_names = [t.strip() for t in toolset.split(",") if t.strip()]
                if toolset_names:
                    selected_tools.extend(_resolve_toolsets(toolset_names))
            # Auto-discover project-local .praisonai/tools/*.py (additive;
            # explicit --tools take precedence). Gated by the shared
            # PRAISONAI_ALLOW_LOCAL_TOOLS opt-in in the safe loader.
            selected_tools.extend(
                _auto_discover_project_tools(selected_tools, verbose=verbose)
            )
            if selected_tools:
                agent_config["tools"] = list(agent_config.get("tools", [])) + selected_tools

            agent = Agent(**agent_config)
            # Reasoning effort applied via the property setter (not a
            # constructor kwarg) so defaults are unchanged when omitted.
            if thinking_budget is not None:
                agent.thinking_budget = thinking_budget
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
            _record_session_usage(session_id or auto_save_name, model, output)
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
        args.mcp_servers = mcp_servers or None
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
        args.thinking_budget = thinking_budget
        
        praison.args = args

        result = praison.handle_direct_prompt(prompt)
        
        _record_session_usage(session_id or auto_save_name, model, output)
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


def _record_session_usage(session_id, model, output) -> None:
    """Accumulate this run's token/cost usage into the active session and show
    a compact running total footer (Issue #2421).

    Best-effort: never let usage accounting break a completed run. Stays quiet
    in JSON mode so machine-readable output is unaffected.
    """
    if not session_id:
        return
    try:
        from ..state.project_sessions import (
            accumulate_session_usage,
            format_usage_footer,
        )

        usage = accumulate_session_usage(session_id, model=model)
    except Exception:
        return

    if not usage or not usage.get("total_tokens"):
        return
    if output is not None and getattr(output, "is_json_mode", False):
        return
    try:
        footer = format_usage_footer(usage)
        if output is not None:
            output.print_info(footer)
        else:
            typer.echo(footer)
    except Exception:
        pass


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
    from praisonai_code.cli.features.cli_profiler import (
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
        from praisonai_code.cli.main import PraisonAI
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
    
    _record_session_usage(session_id or auto_save_name, model, None)
    
    profiler.stop()
    
    # Print result
    if result:
        print(result)
    
    # Print profiling report
    profiler.print_report()


def _wire_subagent_delegation(
    agent_config: Dict[str, Any],
    subagents: Optional[str],
) -> None:
    """Attach a `spawn_subagent` tool that can delegate to named agents.

    Resolves delegatable ``.praisonai/agents/*.md`` definitions into a
    core ``create_subagent_tool`` resolver and appends the tool to
    ``agent_config['tools']``. No-op when there are no delegatable agents so
    the default run is unchanged.

    ``subagents`` is the raw ``--subagents`` string (comma-separated names);
    when None, agents marked ``mode: subagent`` are exposed instead.
    """
    allow_list = None
    if subagents:
        allow_list = [name.strip() for name in subagents.split(",") if name.strip()]

    try:
        from praisonai_code.cli.features.custom_definitions import (
            build_subagent_resolver,
        )

        resolver, descriptions = build_subagent_resolver(allow_list)
    except Exception:
        return

    if resolver is None:
        return

    from praisonaiagents.tools.subagent_tool import create_subagent_tool

    tool = create_subagent_tool(
        agent_resolver=resolver,
        allowed_agents=list(descriptions.keys()),
        resolvable_agents=descriptions,
    )
    agent_config["tools"] = list(agent_config.get("tools") or []) + [tool]


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
    thinking_budget: Optional[int] = None,
    subagents: Optional[str] = None,
):
    """Run a custom agent definition."""
    output = get_output_controller()
    
    try:
        from praisonaiagents import Agent
        
        # Override model if specified
        if model:
            agent_config["llm"] = model

        # Offer discovered named agents as delegation targets. The primary
        # agent can then call spawn_subagent(agent_name="researcher", ...) to
        # hand a sub-task to a user-defined .praisonai/agents/*.md agent, which
        # runs under its own model/tools/permissions. An explicit --subagents
        # allow-list wins; otherwise agents marked `mode: subagent` are used.
        _wire_subagent_delegation(agent_config, subagents)
        
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
            from praisonai_code.cli.features._approval_bridge import resolve_approval_config
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
            from praisonai_code.cli.features._approval_bridge import resolve_approval_config
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
        # Reasoning effort applied via the property setter (not a constructor
        # kwarg) so defaults are unchanged when --thinking is omitted.
        if thinking_budget is not None:
            agent.thinking_budget = thinking_budget

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
        _record_session_usage(session_id or auto_save_name, model, output)
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
    from praisonai_code.cli.features.cli_profiler import (
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
    
    _record_session_usage(session_id or auto_save_name, model, None)
    
    profiler.stop()
    
    # Print response
    if response:
        print(response)
    
    # Print profiling report
    profiler.print_report()
