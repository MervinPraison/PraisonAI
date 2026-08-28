"""
Run command group for PraisonAI CLI.

Provides agent execution commands.
"""

from contextlib import contextmanager
from typing import Any, Dict, Optional, List

import typer

from ..output.console import get_output_controller
from ..state.identifiers import get_current_context
from ..configuration.resolver import resolve_config
from ..utils.env_utils import scopes_no_plugins

app = typer.Typer(help="Run agents")


_FRAMEWORK_HELP = "Framework: praisonai, crewai, autogen"

_ALLOW_LOCAL_TOOLS_ENV = "PRAISONAI_ALLOW_LOCAL_TOOLS"


def _run_succeeded(result: Any) -> bool:
    """Whether an agent run result represents a genuine success.

    The public ``Agent.start``/``run`` surface collapses failures (swallowed
    LLM/auth error, guardrail block, tool failure, ``max_iter`` without
    completion) to a falsy result (``None``/empty), while a real answer is a
    non-empty string. Treat a falsy result as failure so ``praisonai run`` can
    exit non-zero and emit a machine-readable outcome instead of reporting
    success unconditionally.
    """
    if result is None:
        return False
    if isinstance(result, str):
        return bool(result.strip())
    return True


def _run_was_truncated(agent: Any) -> bool:
    """Whether the agent's last run stopped by hitting the step/iteration limit.

    A non-empty finalisation summary is still returned when a run exhausts its
    ``max_steps``/``max_iter`` budget, so string-emptiness alone reports a
    *truncated* run as success. The core already records the terminal reason on
    the agent via ``last_stop_reason`` (``"max_steps"`` on truncation), so
    consult it to distinguish a genuine completion from a wrapped-up one.

    Best-effort: any agent without the accessor (or a raising one) is treated as
    not-truncated so the completed/failed contract is preserved unchanged.
    """
    if agent is None:
        return False
    try:
        return getattr(agent, "last_stop_reason", None) == "max_steps"
    except Exception:
        return False


# Provider-side terminal reasons the core records on ``agent.last_stop_reason``
# from the LLM ``finish_reason``/refusal signal. Kept in lockstep with the core
# ``run_outcome.PROVIDER_BLOCK_REASONS`` taxonomy; unknown reasons are ignored so
# the completed/failed contract is preserved when the core reports nothing new.
_BLOCK_REASON_MESSAGES = {
    "content_filtered": (
        "Run blocked: the provider's content filter blocked the response.",
        "The model provider blocked this response with a content filter. "
        "Rephrase the request or adjust provider safety settings.",
    ),
    "refused": (
        "Run refused: the model declined to answer (safety refusal).",
        "The model refused to answer. Rephrase the request or try a different "
        "model.",
    ),
    "length_truncated": (
        "Run truncated: the response hit the model's output length limit.",
        "The response was cut off by the model's output length limit. "
        "Re-run with a higher --max-tokens.",
    ),
}


def _run_block_reason(agent: Any) -> Optional[str]:
    """Return a provider block/refusal/truncation reason for the last run.

    The core records a distinct terminal reason on ``agent.last_stop_reason``
    when the provider ``finish_reason``/refusal signalled a content filter,
    refusal, or length cutoff. Returns that reason when recognised, else None so
    the existing completed/failed/max_steps contract is unchanged.

    Best-effort: any agent without the accessor (or a raising one) yields None.
    """
    if agent is None:
        return None
    try:
        reason = getattr(agent, "last_stop_reason", None)
    except Exception:
        return None
    return reason if reason in _BLOCK_REASON_MESSAGES else None


def _report_run_blocked(output: Any, result: Any, reason: str) -> None:
    """Report a provider-blocked/refused/truncated run distinctly and exit 2.

    Mirrors ``_report_run_truncated``: any partial text is preserved in the
    emitted result, but the *status* is the specific reason so ``--output json``
    consumers and CI can branch on *why* nothing usable came back. Exits with
    code 2 (an incomplete run), distinct from a hard failure (exit 1) and a
    clean completion (exit 0).
    """
    message, remediation = _BLOCK_REASON_MESSAGES[reason]
    text = str(result) if result else None
    output.emit_result(
        message=message,
        data={"status": reason, "result": text},
    )
    if not getattr(output, "is_json_mode", False):
        output.print_warning(f"{message} {remediation}")
    raise typer.Exit(2)


def _report_run_failure(output: Any) -> None:
    """Report an agent-run failure and exit non-zero.

    Mirrors the existing arg-error exit convention (``typer.Exit(1)``) but for a
    *run* failure: emits a machine-readable outcome under ``--output json`` and
    prints a human-facing error, so CI/scripts can branch on the exit code and
    the JSON ``status`` instead of scraping stderr.
    """
    message = "Run failed: the agent did not produce a result."
    output.emit_result(
        message=message,
        data={"status": "failed", "result": None},
    )
    output.emit_error(message=message, data={"status": "failed"})
    output.print_error(
        message,
        code="run_failed",
        remediation=(
            "Re-run with --verbose to see the underlying error, "
            "or check credentials with: praisonai setup"
        ),
    )
    raise typer.Exit(1)


def _report_run_truncated(output: Any, result: Any) -> None:
    """Report a step-limit-truncated run distinctly from a genuine completion.

    The finalisation summary is a real (non-empty) answer, so it is preserved in
    the emitted result; only the *status* changes to ``"truncated"`` so
    ``--output json`` consumers and CI can branch on an incomplete run. A
    one-line stderr notice tells an interactive user the answer is a wrap-up, not
    a finished task. Exits with code 2 to distinguish truncation (exit 2) from a
    hard failure (exit 1) and a clean completion (exit 0).
    """
    text = str(result) if result else None
    output.emit_result(
        message="Run truncated: hit the step/iteration limit before completing.",
        data={"status": "truncated", "result": text},
    )
    if not getattr(output, "is_json_mode", False):
        output.print_warning(
            "Run hit the step/iteration limit; the answer above is a summary of "
            "partial progress, not a completed task. Re-run with a higher "
            "--max-iter/max_steps to finish."
        )
    raise typer.Exit(2)


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


def _plan_permission_conflicts(
    approval: Optional[str],
    allow: Optional[List[str]],
    deny: Optional[List[str]],
    permission_default: Optional[str],
) -> List[str]:
    """Return the permission flags that contradict ``--plan``.

    ``--plan`` is a self-contained read-only preset (``PermissionMode.PLAN``);
    combining it with an explicit approval backend or bespoke allow/deny rules
    is unenforceable, so the caller fails closed. Returns the human-readable
    flag names that were set, or an empty list when ``--plan`` may proceed.
    """
    return [
        name
        for name, value in (
            ("--approval", approval),
            ("--allow", allow),
            ("--deny", deny),
            ("--permission-default", permission_default),
        )
        if value
    ]


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
                from praisonai_code.cli.features.custom_definitions import (
                    local_tools_enabled,
                )
                if not local_tools_enabled():
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

    When tool files are present but skipped because the opt-in is unset, a
    single concise hint is printed on the default path (not just ``--verbose``)
    so a ``praisonai init`` -> add-tool -> ``run`` flow explains the one step
    needed instead of silently loading nothing.

    Discovery is additive: explicit ``--tools`` items already in ``existing``
    take precedence and are not re-added (dedup by callable identity).
    """
    try:
        from praisonai_code.cli.features.custom_definitions import (
            count_project_tool_files,
            discover_project_tools,
            local_tools_enabled,
        )
    except Exception:
        return []

    # Files present but the opt-in is unset: tell the user exactly how to
    # enable them rather than silently skipping. Say nothing when there are no
    # local tool files. ``local_tools_enabled`` mirrors the loader's exact
    # acceptance semantics (``lower() == "true"``), so a truthy-but-not-``true``
    # value like ``false``/``0`` still surfaces the hint instead of being
    # treated as enabled and then silently skipped by the loader.
    if not local_tools_enabled():
        try:
            project_count, user_count = count_project_tool_files()
        except Exception:
            project_count, user_count = 0, 0
        total = project_count + user_count
        if total:
            plural = "s" if total != 1 else ""
            # Name the actual source(s) so a user with only ~/.praisonai/tools/
            # global files is not pointed at a project dir that may not exist.
            locations = []
            if project_count:
                locations.append(".praisonai/tools/")
            if user_count:
                locations.append("~/.praisonai/tools/")
            where = " and ".join(locations)
            get_output_controller().print_info(
                f"Found {total} local tool file{plural} in {where} "
                "but local tools are disabled. Enable with "
                "PRAISONAI_ALLOW_LOCAL_TOOLS=true or --allow-local-tools."
            )
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


def _resolve_config_instructions() -> List[str]:
    """Return config-declared ``instructions`` sources (layered, concat-merged).

    The resolver already concatenates list-valued keys across the config
    hierarchy (global → user → project), so an org-wide instruction set under
    a project-specific one is preserved rather than overridden. The key lives
    under ``extra`` because it is a wrapper-only top-level key. Non-list or
    absent values yield an empty list (fully backward-compatible).
    """
    try:
        config = resolve_config()
    except (ValueError, OSError):
        return []
    value = (getattr(config, "extra", None) or {}).get("instructions")
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [str(v) for v in value if isinstance(v, (str,)) and v.strip()]
    return []


def _merge_instructions(cli_instructions: Optional[List[str]]) -> List[str]:
    """Merge config-declared instruction sources with repeatable CLI ones.

    Config sources come first (org/project layering) and CLI ``--instructions``
    entries are appended on top, matching the documented precedence (flag
    merges on top of config). Returns an empty list when neither is present.
    """
    merged = _resolve_config_instructions()
    if cli_instructions:
        merged = merged + [s for s in cli_instructions if isinstance(s, str) and s.strip()]
    return merged


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


def _revert_checkpoint(
    ref: str, *, session: Optional[str] = None, workspace_dir: Optional[str] = None
) -> None:
    """Revert files + conversation together to a prior turn, then exit.

    Distinct from the file-only ``--restore``: this shows the diff first and,
    when a ``--session`` is provided, also rewinds that session's conversation
    to the same boundary so chat history and workspace stay in lockstep — the
    same coherent-undo contract the interactive REPL/TUI ``/undo`` uses. Without
    a session it degrades to a previewed file-only revert (nothing to keep in
    sync).
    """
    import asyncio
    import os

    from praisonai_code.cli.features.checkpoints import CheckpointsHandler

    output = get_output_controller()
    workspace_dir = workspace_dir or os.getcwd()
    handler = CheckpointsHandler(
        workspace_dir=workspace_dir,
        storage_dir=_checkpoints_storage_dir(),
    )

    # Resolve how many turns back to go: 'last'/'' -> 1, else an integer.
    token = (ref or "last").strip().lower()
    n = 1
    if token and token not in ("last", "latest"):
        try:
            n = int(token)
        except ValueError:
            output.print_error("Usage: --revert [last|N]")
            raise typer.Exit(1)
        if n < 1:
            output.print_error("--revert N must be >= 1")
            raise typer.Exit(1)

    async def _run() -> bool:
        service = await handler._get_service()
        checkpoints = await service.list_checkpoints(limit=100)
        if not checkpoints or len(checkpoints) < n:
            handler._print_error(
                f"No checkpoint {n} turn(s) back to revert to"
            )
            return False
        # checkpoints[0] is the most recent; index n-1 is the target boundary.
        target = checkpoints[n - 1]
        # Show the diff that will be undone before touching anything.
        try:
            await service.diff(target.id, None)
        except Exception:
            pass
        return await handler.restore(target.id)

    if not asyncio.run(_run()):
        raise typer.Exit(1)

    # Rewind the conversation to keep it in lockstep with the reverted files.
    # Best-effort and only when a session was named; a failure here must not
    # undo the already-restored workspace.
    if session:
        # File checkpoints are workspace-wide (they carry no session tag), so
        # when several sessions share a workspace the Nth-back file checkpoint
        # may belong to a different session than the one whose conversation we
        # rewind. Surface that explicitly rather than implying a guaranteed
        # per-session pairing; the interactive REPL/TUI ``/undo`` — which keeps
        # its own captured per-turn boundaries — remains the fully coherent path.
        output.print_info(
            "Note: file checkpoints are workspace-wide; in a workspace shared by "
            "multiple sessions the reverted files may not correspond exactly to "
            f"session '{session}'. Use the interactive /undo for per-session coherence."
        )
        try:
            from praisonaiagents.session.hierarchy import HierarchicalSessionStore

            from ..utils.project import get_project_sessions_dir

            store = HierarchicalSessionStore(str(get_project_sessions_dir()))
            data = store.get_extended_session(session)
            messages = list(getattr(data, "messages", []) or [])
            # Rewind the conversation to the boundary *before* the last ``n``
            # user turns. Counting real user messages (rather than assuming two
            # messages per turn) keeps history coherent when a turn also
            # persisted tool/system/assistant messages — subtracting a fixed
            # ``2 * n`` would otherwise leave orphaned tool replies or drop an
            # unrelated earlier turn.
            user_indices = [
                i for i, m in enumerate(messages)
                if isinstance(m, dict) and m.get("role") == "user"
            ]
            if len(user_indices) >= n:
                # The first user message of the last ``n`` turns marks where the
                # undone turns begin; keep everything strictly before it.
                boundary = user_indices[len(user_indices) - n]
                keep = boundary  # number of messages to retain
                if keep >= 1:
                    # revert_to_message keeps messages[:index + 1]; target keep-1.
                    store.revert_to_message(session, keep - 1)
                    output.print_info(
                        f"Reverted session '{session}' conversation to keep "
                        f"{keep} message(s)."
                    )
                elif messages:
                    # Rewinding to empty would strand a ghost first message via
                    # revert_to_message (index 0 keeps one), so clear explicitly
                    # when the store supports it; otherwise leave history intact.
                    clear = getattr(store, "clear_messages", None)
                    if callable(clear):
                        clear(session)
                        output.print_info(
                            f"Reverted files and cleared session '{session}' "
                            "conversation."
                        )
                    else:
                        output.print_info(
                            f"Reverted files; session '{session}' conversation "
                            "left intact (too short to rewind coherently)."
                        )
            elif messages:
                output.print_info(
                    f"Reverted files; session '{session}' conversation has "
                    f"fewer than {n} turn(s) to rewind — left intact."
                )
        except Exception as e:  # pragma: no cover - defensive
            if getattr(output, "is_verbose", False):
                output.print_info(f"Conversation rewind skipped: {e}")


def _try_attach_runtime(
    prompt: str,
    *,
    model: Optional[str],
    output_mode: Optional[str],
    session_id: Optional[str],
    event_id: Optional[str] = None,
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
        result = client.run(
            prompt, model=model, session_id=session_id, event_id=event_id
        )
    except RuntimeUnavailable:
        # Runtime went away mid-flight; fall back to in-process execution.
        return False

    # The warm runtime handled the request; apply the same failure contract as
    # the in-process paths so an empty result exits non-zero instead of silently
    # reporting success.
    if not _run_succeeded(result):
        _report_run_failure(output)
    output.emit_result(
        message="Prompt completed",
        data={"result": str(result) if result else None},
    )
    if result and not output.is_json_mode:
        print(result)
    return True


@contextmanager
def _worktree_isolation(enabled: bool, name: str, *, keep: bool = False):
    """Run the enclosed block inside an isolated git worktree/branch.

    Provisions a fresh worktree via the core ``GitWorktreeAdapter`` and chdirs
    into it for the duration of the run so the agent edits an isolated branch
    instead of the working tree. On exit it reports the branch name and a
    summary of changes (tracked *and* untracked), then tears the worktree down.
    Degrades to a transparent no-op when isolation is disabled or the directory
    is not a git repository (the adapter reports ``available=False``), so callers
    can wrap unconditionally.

    Per-run isolation: a short random token is appended to ``name`` so two
    concurrent or repeated runs of the same target never resolve to the same
    worktree/branch and mix each other's uncommitted changes.

    Data-safety on teardown: the agent's output may be entirely *untracked* new
    files, which ``git diff`` does not see. So before removing the worktree we
    snapshot any change (tracked or untracked, via ``git status --porcelain``)
    onto the branch with an automatic commit and *retain that branch* — only the
    worktree checkout directory is pruned. A run that produced no changes is
    torn down completely (worktree + branch). ``--keep`` additionally retains the
    worktree checkout itself for in-place review.
    """
    if not enabled:
        yield None
        return

    import os
    import subprocess
    import uuid

    from praisonaiagents.workspace import GitWorktreeAdapter

    output = get_output_controller()
    adapter = GitWorktreeAdapter()
    if not adapter.available:
        output.print_warning(
            "Not a git repository; running without worktree isolation."
        )
        yield None
        return

    def _git(*args, cwd):
        try:
            return subprocess.run(
                ["git", *args], cwd=cwd, capture_output=True, text=True
            )
        except (FileNotFoundError, OSError):
            return None

    def _branch_of(worktree_path: str) -> str:
        result = _git("rev-parse", "--abbrev-ref", "HEAD", cwd=worktree_path)
        if result is not None and result.returncode == 0:
            return result.stdout.strip() or "?"
        return "?"

    def _has_changes(worktree_path: str) -> bool:
        # ``--porcelain`` reports staged, unstaged *and* untracked entries, so a
        # run that only creates brand-new files (invisible to ``git diff``) is
        # still recognised as having produced output.
        result = _git("status", "--porcelain", cwd=worktree_path)
        if result is None or result.returncode != 0:
            return False
        return bool((result.stdout or "").strip())

    def _summary(worktree_path: str) -> str:
        result = _git("status", "--short", cwd=worktree_path)
        if result is None or result.returncode != 0:
            return ""
        return (result.stdout or "").strip()

    # Make the run's worktree/branch unique per invocation so identical targets
    # (same prompt/YAML) run concurrently without sharing state.
    unique_name = f"{name}-{uuid.uuid4().hex[:8]}"

    original_cwd = os.getcwd()
    path = adapter.create(unique_name)
    branch = _branch_of(path)
    if not output.is_json_mode:
        output.print_info(f"Isolated run on branch '{branch}' ({path})")
    os.chdir(path)
    try:
        yield path
    finally:
        os.chdir(original_cwd)

        summary = _summary(path)
        changed = _has_changes(path)
        if not output.is_json_mode:
            if summary:
                output.print_info(f"Changes on '{branch}':\n{summary}")
            else:
                output.print_info(f"No changes on '{branch}'.")

        if keep:
            if not output.is_json_mode:
                output.print_info(
                    f"Worktree kept at {path} (branch '{branch}'). "
                    "Review/merge then remove with: git worktree remove."
                )
            return

        if changed:
            # Never destroy the agent's output. Persist every change (tracked +
            # untracked) as a commit on the isolated branch and retain the
            # branch; only the worktree checkout directory is pruned.
            _git("add", "-A", cwd=path)
            committed = _git(
                "commit", "--no-verify", "-m", f"praisonai run: {name}", cwd=path
            )
            if committed is None or committed.returncode != 0:
                # Couldn't persist the work (e.g. no git identity configured):
                # keep the worktree checkout in place so output is never lost.
                if not output.is_json_mode:
                    output.print_warning(
                        f"Could not commit isolated changes; worktree kept at "
                        f"{path} (branch '{branch}') for manual review."
                    )
                return
            # ``worktree remove`` deletes the checkout but leaves the branch
            # intact for review/merge (unlike ``adapter.remove`` which also
            # force-deletes the branch and would lose the committed work).
            _git("worktree", "remove", "--force", path, cwd=original_cwd)
            if not output.is_json_mode:
                output.print_info(
                    f"Committed changes to branch '{branch}'. "
                    f"Review/merge with: git merge {branch}"
                )
        else:
            # No output produced: safe to remove worktree and branch entirely.
            adapter.remove(unique_name)


@app.callback(invoke_without_command=True)
@scopes_no_plugins
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
    allow_local_tools: bool = typer.Option(False, "--allow-local-tools", help="Load project-local .praisonai/tools/*.py (equivalent to PRAISONAI_ALLOW_LOCAL_TOOLS=true)"),
    max_tokens: int = typer.Option(16000, "--max-tokens", help="Maximum output tokens"),
    profile: bool = typer.Option(False, "--profile", help="Enable CLI profiling (timing breakdown)"),
    profile_deep: bool = typer.Option(False, "--profile-deep", help="Enable deep profiling (cProfile stats, higher overhead)"),
    output_mode: Optional[str] = typer.Option(None, "--output", "-o", help="Output mode: silent (default), actions, verbose, json, stream"),
    approval: Optional[str] = typer.Option(None, "--approval", help="Approval backend: console, plan, accept-edits, bypass, auto, agent, none, slack, telegram, discord, webhook, http, secure, presentation"),
    approve_all_tools: bool = typer.Option(False, "--approve-all-tools", help="Require approval for ALL tool calls, not just dangerous tools"),
    approval_timeout: Optional[str] = typer.Option(None, "--approval-timeout", help="Seconds to wait for approval. Use 'none' for indefinite wait"),
    no_rules: bool = typer.Option(False, "--no-rules", help="Disable auto-injection of project instruction files"),
    pure: bool = typer.Option(False, "--pure", "--no-plugins", help="Skip discovery/loading of external plugins for this run only (equivalent to PRAISONAI_NO_PLUGINS=1); persisted enable/disable state is unchanged"),
    instructions: Optional[List[str]] = typer.Option(None, "--instructions", help="Extra instruction/context source (file path, glob, or http(s):// URL) to load alongside AGENTS.md/CLAUDE.md. Repeatable; merges on top of config-declared 'instructions'."),
    # Permission flags for CI-safe declarative policies
    allow: Optional[List[str]] = typer.Option(None, "--allow", help="Permission pattern to allow (e.g., 'read:*', 'bash:git *'). Can be repeated."),
    deny: Optional[List[str]] = typer.Option(None, "--deny", help="Permission pattern to deny (e.g., 'bash:rm *'). Can be repeated."),
    permissions: Optional[str] = typer.Option(None, "--permissions", help="Permission file path (YAML or JSON) with allow/deny rules"),
    permission_default: Optional[str] = typer.Option(None, "--permission-default", help="Default action for unmatched patterns: allow, deny, ask (default: ask)"),
    plan: bool = typer.Option(False, "--plan", help="Read-only planning mode: the agent may explore/read/search but every mutating tool is denied (maps to --approval plan)"),
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
    restore: Optional[str] = typer.Option(None, "--restore", help="Restore the workspace files only to a checkpoint id (or 'last') and exit"),
    revert: Optional[str] = typer.Option(None, "--revert", help="Revert files + conversation together to a prior turn ('last' or N), showing the diff first, and exit", flag_value="last", is_flag=False),
    # Warm-runtime live session: tag this run so other terminals can `attach`.
    attach: Optional[str] = typer.Option(None, "--attach", help="Run on the warm runtime under this session id so other terminals can observe it via `praisonai attach <id>`"),
    # Per-run git-worktree isolation: run on a fresh branch/worktree.
    worktree: bool = typer.Option(False, "--worktree", help="Run on an isolated git worktree/branch (branch-per-task); no-op when not a git repo"),
    keep: bool = typer.Option(False, "--keep", help="With --worktree, keep the worktree/branch after the run for review instead of tearing it down"),
    append_system_prompt: Optional[str] = typer.Option(None, "--append-system-prompt", help="Append text (or @file) to the system prompt for this invocation only. Env fallback: PRAISONAI_APPEND_SYSTEM_PROMPT"),
    # Multimodal attachment for one-shot runs
    image: Optional[List[str]] = typer.Option(None, "--image", help="Attach an image (local path or http(s):// URL) to a one-shot run so the agent can see it. Repeatable."),
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
        praisonai run "Describe this screenshot" --image bug.png
        praisonai run "Compare these" --image a.png --image b.png
    """
    output = get_output_controller()
    _ = get_current_context()  # Initialize context

    # --pure / --no-plugins: suppression is scoped by the @scopes_no_plugins
    # decorator, which sets PRAISONAI_NO_PLUGINS (read by the core PluginManager)
    # for the duration of this call and always restores the prior value on
    # return, so it never leaks into a later in-process run_main() call.
    # Persisted enable/disable state is untouched.

    # --allow-local-tools is a discoverable equivalent to the env-var opt-in.
    # It is a per-invocation grant: the actual gate is applied (and restored)
    # only around tool discovery below, so a later in-process run_main() call
    # without the flag never inherits the authorization to exec local Python.

    # Rewind: restore the workspace to a prior checkpoint and exit. Handled
    # before any execution (and before stdin ingestion) so `praisonai run
    # --restore last` is a pure undo that never drains a pipe it won't use.
    if restore:
        _restore_checkpoint(restore)
        return

    # Coherent rewind: roll files *and* conversation back to a prior turn and
    # exit. Distinct from the file-only ``--restore`` above — this reuses the
    # SessionCheckpointManager so chat history and workspace stay in lockstep.
    if revert is not None:
        _revert_checkpoint(revert, session=session)
        return

    # Resolve --append-system-prompt (literal text or @file) and export it so
    # every downstream agent-construction path appends it to the system prompt.
    from ..utils.append_prompt import apply_append_system_prompt
    resolved_append_prompt = apply_append_system_prompt(append_system_prompt)

    # Merge config-declared instruction sources (layered global→project) with
    # repeatable ``--instructions`` flags so both the prompt and profiled run
    # paths load the same extra guidance alongside AGENTS.md/CLAUDE.md.
    merged_instructions = _merge_instructions(instructions)

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

    # --plan is a discoverable alias for the existing read-only planning mode
    # (--approval plan → PermissionMode.PLAN). It maps onto the same permission
    # plumbing rather than a bespoke deny-set, so the agent may explore/read but
    # every mutating tool is denied. Guard against contradictory permission
    # flags so an unenforceable combination fails closed rather than silently
    # dropping one intent.
    if plan:
        _conflicts = _plan_permission_conflicts(
            approval, allow, deny, permission_default
        )
        if _conflicts:
            output.print_error(
                "--plan cannot be combined with "
                + ", ".join(_conflicts)
                + " (it already selects the read-only planning mode)"
            )
            raise typer.Exit(1)
        approval = "plan"

    _require_wrapper_for_default_run(
        target, agent=agent, command=command, output_mode=output_mode
    )

    # Validate session options before any model/credential resolution so an
    # invalid combination fails closed and session-model restoration below sees
    # a well-formed request.
    if fork and not session:
        output.print_error("--fork requires --session to specify which session to fork from")
        raise typer.Exit(1)

    if continue_session and session:
        output.print_error("Cannot use both --continue and --session together")
        raise typer.Exit(1)

    # Resolve the effective model BEFORE the credential/local-endpoint gate so a
    # resumed session (or config) model is honoured rather than being shadowed
    # by the keyless local-first fallback (Issue #3685). Precedence:
    #   explicit --model  >  config model  >  recorded session model  >  default
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

    # Restore the resumed session's model when none was explicitly chosen
    # (Issue #3685). Without this, resume re-resolves the *current* default, so
    # a change to the user's default between runs silently switches the model
    # mid-conversation. An explicit --model (or config model above) still wins
    # and updates the session's recorded model for subsequent turns. Placing it
    # before the credential gate ensures a reachable local endpoint no longer
    # silently shadows the recorded model on resume.
    if model is None and (continue_session or session):
        try:
            from ..state.project_sessions import find_last_session, find_session_model

            resumed_id = session or find_last_session()
            if resumed_id:
                recorded = find_session_model(resumed_id)
                if recorded:
                    model = recorded
                    output.print_info(f"Restored session model: {model}")
        except Exception:
            # Model restore is best-effort; fall back to default resolution.
            pass

    # Restore the graded reasoning effort a resumed session was running when the
    # user did not pass an explicit --thinking (Issue #4452), mirroring the model
    # restore above (#3685). The recorded graded level is re-resolved to the core
    # thinking_budget so it flows through the same path already threaded below.
    if thinking is None and thinking_budget is None and (continue_session or session):
        try:
            from ..state.project_sessions import (
                find_last_session,
                find_session_reasoning_effort,
            )

            resumed_id = session or find_last_session()
            if resumed_id:
                recorded_effort = find_session_reasoning_effort(resumed_id)
                if recorded_effort:
                    restored = thinking_to_budget(recorded_effort)
                    if restored is not None:
                        thinking_budget = restored
                        output.print_info(
                            f"Restored session reasoning effort: {recorded_effort}"
                        )
        except Exception:
            # Effort restore is best-effort; fall back to the default.
            pass

    # Early credential check before any processing. Uses the shared first-run
    # gate (issue #4024) so `run`, `code`, `chat`, and the bare invocation route
    # a keyless newcomer to `setup` (or a detected keyless local endpoint)
    # identically instead of dead-ending on a raw provider error. Headless
    # (non-TTY / --output json) fails fast with the actionable hint; interactive
    # offers the wizard and re-checks.
    if target:  # Only check if we actually have something to run
        import sys
        from praisonai_code.llm.credentials import ensure_configured_or_onboard

        _headless = (not sys.stdin.isatty()) or output.is_json_mode
        model = ensure_configured_or_onboard(model=model, interactive=not _headless)

    # Worktree isolation runs the agent in a chdir'd worktree in-process; the
    # warm runtime is a separate process whose cwd we can't redirect, so reject
    # the combination up front rather than silently ignoring isolation.
    if worktree and attach:
        output.print_error("--worktree cannot be combined with --attach")
        raise typer.Exit(1)
    if keep and not worktree:
        output.print_error("--keep requires --worktree")
        raise typer.Exit(1)
    # Scope isolation to the primary `run "<task>"` / `run agents.yaml` surfaces.
    # Custom agent/command and profiling flows have their own execution paths;
    # keep the feature focused rather than threading a worktree through each.
    if worktree and (agent or command or profile or profile_deep):
        output.print_error(
            "--worktree is only supported for direct prompt and YAML file runs"
        )
        raise typer.Exit(1)

    # --attach tags a warm-runtime run so other terminals can observe it, but
    # only the direct-prompt path forwards to the warm runtime. Reject it up
    # front on profile/custom-agent/custom-command flows so users never
    # pass --attach and silently get a session that produces no events.
    if attach and (agent or command or profile or profile_deep):
        output.print_error("--attach is only supported for direct prompt runs")
        raise typer.Exit(1)

    # --image is a per-invocation multimodal attachment for direct prompt runs.
    # Only the direct-prompt (and interpolated --command) path threads it to the
    # vision-capable handle_direct_prompt/ImageHandler; the custom-agent, YAML
    # file, and profiling flows have separate execution paths that do not carry
    # it. Reject those combinations up front so an --image is never silently
    # dropped and the user gets a result without the attachment they asked for.
    if image and (agent or profile or profile_deep or _is_yaml_file(target or "")):
        output.print_error(
            "--image is only supported for direct prompt runs "
            "(not with --agent, --profile, or a YAML file)"
        )
        raise typer.Exit(1)

    # --output actions builds a bare Agent (which can't carry the attachment) and
    # the vision path can't honour the structured actions output contract, so the
    # two are mutually exclusive. Reject up front rather than returning a plain
    # vision response when the user asked for actions-form output.
    if image and output_mode == "actions":
        output.print_error("--image cannot be combined with --output actions")
        raise typer.Exit(1)

    # ImageHandler treats a comma as the multi-image separator, so a single
    # path/URL that itself contains a comma would be split into fragments and
    # fail validation (or attach the wrong files). Reject it with a clear error
    # instead of silently corrupting the attachment; users pass multiple images
    # with repeated --image flags.
    if image:
        for _img in image:
            if "," in _img:
                output.print_error(
                    f"Invalid --image value {_img!r}: paths/URLs must not contain a "
                    "comma. Pass multiple images with repeated --image flags."
                )
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
            no_rules=no_rules,
            instructions=merged_instructions,
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
            allow_local_tools=allow_local_tools,
            instructions=merged_instructions,
            append_system_prompt=resolved_append_prompt,
            image=image,
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
                approval=approval,
                approve_all_tools=approve_all_tools,
                approval_timeout=approval_timeout,
                output_mode=output_mode,
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
                no_rules=no_rules,
                instructions=merged_instructions,
                approval=approval,
                approve_all_tools=approve_all_tools,
                approval_timeout=approval_timeout,
            )
        return
    
    # Resolve a YAML file target to an absolute path *before* isolation chdirs
    # away. The config is loaded from the original checkout so an untracked or
    # git-ignored ``./agents.yaml`` (absent from the fresh worktree) still loads;
    # the agent then produces its output inside the isolated worktree.
    run_target = target
    if worktree and is_file:
        import os as _os_ff
        run_target = _os_ff.path.abspath(target)

    # Provision a per-run git worktree/branch when --worktree is set and the cwd
    # is a git repo; otherwise this is a transparent no-op. The agent runs with
    # its cwd redirected into the isolated worktree for the duration of the run.
    with _worktree_isolation(worktree, target, keep=keep):
        if is_file:
            # Resolve permission rules (CLI flags + project config) so YAML
            # workflows are permission-gated on the same declarative rules as
            # single-agent `run`, instead of bypassing the approval gate.
            file_permissions = _parse_permissions(allow, deny, permissions, permission_default)
            _, _, file_permissions, _ = _apply_config_defaults(None, None, file_permissions)
            # Run from file
            _run_from_file(
                run_target,
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
                approval=approval,
                approve_all_tools=approve_all_tools,
                approval_timeout=approval_timeout,
                permissions_config=file_permissions,
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
                allow_local_tools=allow_local_tools,
                isolated=worktree,
                instructions=merged_instructions,
                append_system_prompt=resolved_append_prompt,
                image=image,
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
    approval: Optional[str] = None,
    approve_all_tools: bool = False,
    approval_timeout: Optional[str] = None,
    permissions_config: Optional[dict] = None,
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

        # Derive an approval backend so YAML runs are permission-gated like the
        # single-agent `run` path. An explicit --approval wins; otherwise a
        # console backend is selected when --allow/--deny/--permissions rules are
        # present so deny/ask patterns are enforced instead of silently bypassed.
        effective_approval = approval
        if effective_approval is None and permissions_config:
            effective_approval = "console"

        # Create args-like object for session + permission configuration. The
        # legacy YAML path (PraisonAI.run -> _extract_cli_config) already reads
        # approval / approve_all_tools / approval_timeout and session ids from
        # ``args``, so threading them here gives YAML the same permission gating
        # and continuity as `run "<prompt>"` — no new engine wiring needed.
        if (
            session_id
            or auto_save_name
            or effective_approval
            or approve_all_tools
            or output_mode
        ):
            class Args:
                pass
            
            args = Args()
            args.auto_save = auto_save_name
            args.resume_session = session_id
            args.cli_project_sessions = bool(session_id or auto_save_name)
            args.output = output_mode
            if effective_approval:
                args.approval = effective_approval
            if approve_all_tools:
                args.approve_all_tools = approve_all_tools
            if approval_timeout is not None:
                args.approval_timeout = approval_timeout

            praison.args = args
        
        # Run
        result = praison.run()
        
        _record_session_usage(session_id or auto_save_name, model, output)
        if not _run_succeeded(result):
            _report_run_failure(output)
        output.emit_result(
            message="Run completed",
            data={"result": str(result) if result else None}
        )
        
        if result:
            if not output.is_json_mode:
                output.print_success("Run completed")
    
    except typer.Exit:
        # A deliberate non-zero exit (e.g. a classified run failure) must
        # propagate unchanged; the broad handler below is only for unexpected
        # errors and would otherwise re-report the same failure.
        raise
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
    allow_local_tools: bool = False,
    isolated: bool = False,
    instructions: Optional[List[str]] = None,
    append_system_prompt: Optional[str] = None,
    image: Optional[List[str]] = None,
):
    """Run a direct prompt."""
    output = get_output_controller()
    
    # Note: Credential check already done in run_main() entry point

    # Scope the --allow-local-tools grant to this run so the opt-in never leaks
    # into a later in-process invocation (embedded/notebook/test reuse). The
    # loader reads PRAISONAI_ALLOW_LOCAL_TOOLS at tool-exec time, so set it for
    # the duration of the run and always restore the prior value below.
    import os as _os
    _prev_allow_local_tools = _os.environ.get(_ALLOW_LOCAL_TOOLS_ENV)
    if allow_local_tools:
        _os.environ[_ALLOW_LOCAL_TOOLS_ENV] = "true"

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
        # Session continuity now attaches to a warm, per-session agent in the
        # runtime: a `--continue`/`--session` run rehydrates history once into a
        # warm agent held per session id and reuses it across turns, so the
        # iterative coding loop no longer pays cold-start every turn. The runtime
        # persists per-turn deltas through the same project session store, so a
        # crash/eviction resumes deterministically.
        # A fresh fork (`--fork`) is created in-process because the fork id is
        # minted here; subsequent turns against that id then attach warm.
        # An explicit --thinking budget is a per-invocation override (like tools/
        # approval/memory), so it stays in-process: the warm runtime reuses a
        # cached agent and does not carry a per-call thinking budget, so attaching
        # would silently drop the requested setting.
        # Isolated (--worktree) runs must stay in-process: the warm runtime is a
        # separate process whose cwd we can't redirect into the worktree, so
        # attaching would run the task outside the isolated branch.
        # A per-invocation --append-system-prompt must also stay in-process: the
        # warm runtime is a separate process that never received the CLI's
        # PRAISONAI_APPEND_SYSTEM_PROMPT export, and it reuses a cached agent
        # whose system prompt is already assembled — so attaching would silently
        # drop the requested suffix. The in-process path applies it correctly.
        stateful_attach = bool(session_id) and not fork
        runtime_eligible = (
            (no_save or stateful_attach)
            and thinking_budget is None
            and not isolated
            and not append_system_prompt
            and not image
            and not any([
                mcp, mcp_servers, tools, toolset, approval, approve_all_tools,
                memory, permissions_config, fork, instructions,
            ])
        )
        # Keep the two identities separate:
        #  - session_id is the persistence/conversation identity that drives the
        #    warm stateful path (history rehydrate + per-turn persist). A
        #    --no-save run has session_id=None, so it stays on the isolated,
        #    non-persisted anonymous path.
        #  - --attach <id> is only an event-stream label so other terminals
        #    (`praisonai attach <id>`) observe live events; it must NEVER select
        #    or persist a conversation. Passed as event_id, falling back to the
        #    session id so a plain --session run is still observable under its id.
        runtime_event_id = attach_session or session_id
        if runtime_eligible and _try_attach_runtime(
            prompt,
            model=model,
            output_mode=output_mode,
            session_id=session_id,
            event_id=runtime_event_id,
        ):
            return

        # An --image attachment is handled by the vision path in
        # handle_direct_prompt (ImageHandler); the "actions" fast path builds a
        # bare Agent and would silently drop it, so fall through when set.
        if output_mode == "actions" and not image:
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

            _wire_subtree_context_hook(
                agent_config, no_rules=no_rules, instructions=instructions
            )
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

            succeeded = _run_succeeded(result)
            # A provider content-filter/refusal/length cutoff is a distinct
            # terminal reason recorded by the core; surface it (even for an empty
            # result) so a blocked run isn't collapsed into a generic ``failed``.
            block_reason = _run_block_reason(agent)
            # A non-empty finalisation summary from a step-limit-truncated run
            # is not a genuine completion: classify it *before* emitting the
            # terminal stream event so a `--output stream-json` consumer never
            # receives a contradictory ``run.result {ok: true}`` ahead of the
            # ``status: "truncated"`` outcome (exit 2) reported below.
            truncated = succeeded and _run_was_truncated(agent)
            if bridge is not None:
                bridge.emit_run_result(
                    result, ok=succeeded and not truncated and not block_reason
                )
            _record_session_usage(session_id or auto_save_name, model, output)
            # A provider block/refusal/truncation wins over a generic empty-result
            # failure so the specific, actionable reason is not masked.
            if block_reason:
                _report_run_blocked(output, result, block_reason)
            if not succeeded:
                _report_run_failure(output)
            # Report the truncated run distinctly (exit 2 + status "truncated")
            # so CI/users don't mistake wrapped-up partial work for a completed
            # task.
            if truncated:
                _report_run_truncated(output, result)
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
        args.image = ",".join(image) if image else None
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
        if not _run_succeeded(result):
            _report_run_failure(output)
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
    finally:
        # Restore the prior opt-in state so the grant is strictly per-invocation.
        if _prev_allow_local_tools is None:
            _os.environ.pop(_ALLOW_LOCAL_TOOLS_ENV, None)
        else:
            _os.environ[_ALLOW_LOCAL_TOOLS_ENV] = _prev_allow_local_tools


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
    approval: Optional[str] = None,
    approve_all_tools: bool = False,
    approval_timeout: Optional[str] = None,
    output_mode: Optional[str] = None,
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

    # Thread the approval backend (e.g. --plan -> PermissionMode.PLAN) through
    # the same ``args`` the legacy YAML path reads, so a profiled YAML run is
    # permission-gated identically to the non-profiled path instead of silently
    # dropping the deny policy.
    if session_id or auto_save_name or approval or approve_all_tools or output_mode:
        class Args:
            pass
        
        args = Args()
        args.auto_save = auto_save_name
        args.resume_session = session_id
        args.cli_project_sessions = bool(session_id or auto_save_name)
        args.output = output_mode
        if approval:
            args.approval = approval
        if approve_all_tools:
            args.approve_all_tools = approve_all_tools
        if approval_timeout is not None:
            args.approval_timeout = approval_timeout
        
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

    # Honour the same failure contract as the non-profiled YAML path: an empty
    # agent result is a run failure and must exit non-zero (reported after the
    # profiling output so the profile is still shown).
    if not _run_succeeded(result):
        _report_run_failure(get_output_controller())


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


def _wire_subtree_context_hook(
    agent_config: Dict[str, Any],
    *,
    no_rules: bool = False,
    instructions: Optional[List[str]] = None,
) -> None:
    """Attach the just-in-time subtree instruction hook to ``agent_config``.

    The interactive REPL already lazily attaches a subdirectory's
    ``AGENTS.md``/``CLAUDE.md`` the first time the agent reads/edits a file
    under it (see ``praisonai/cli/interactive/core.py``). The scriptable
    ``praisonai run`` path constructed ``Agent(**agent_config)`` without it, so
    a monorepo run like ``refactor packages/foo/bar.py`` never saw
    ``packages/foo/AGENTS.md`` even though ``praisonai chat`` in the same repo
    did. This registers the *existing* ``AFTER_TOOL`` subtree hook on a fresh,
    session-scoped registry so the non-interactive/CI/SDK-via-CLI surface
    matches interactive behaviour.

    ``instructions`` are config/flag-declared instruction sources (files,
    globs, ``~`` paths, or ``http(s)://`` URLs) that extend the convention-only
    ``AGENTS.md``/``CLAUDE.md`` auto-load. They are resolved and concatenated
    up front into the agent's ``backstory`` (so the guidance is present in the
    system context before any tool call) and passed to the subtree hook as
    ``already_loaded`` so nested files are not duplicated.

    No-op (leaving the default run unchanged) when the up-front rules are
    disabled via ``--no-rules`` / ``PRAISON_NO_RULES``. The subtree-context
    helper is now resident in ``praisonai_code`` so it works on a standalone
    ``pip install praisonai-code`` without the optional ``praisonai_bot`` /
    ``praisonai`` packages. Honours the existing ``PRAISON_CONTEXT_BUDGET``
    character budget shared with the interactive path.
    """
    import os

    if no_rules or os.environ.get("PRAISON_NO_RULES", "").strip().lower() in (
        "1",
        "true",
        "yes",
    ):
        return

    try:
        import importlib

        # The subtree-context helper is now resident in ``praisonai_code`` so
        # the standalone terminal product keeps first-class subtree instruction
        # loading and ``--instructions`` resolution without the optional
        # ``praisonai_bot`` support package or the ``praisonai`` wrapper (C7
        # standalone contract). For backward compatibility we still prefer an
        # installed ``praisonai_bot``/``praisonai`` copy when present (so a host
        # that customised it keeps its behaviour), falling back to the resident
        # implementation otherwise.
        context_files = None
        for _mod in ("praisonai_bot.integration.context_files",
                     "praisonai.integration.context_files",
                     "praisonai_code.integration.context_files"):
            try:
                context_files = importlib.import_module(_mod)
                break
            except ImportError:
                continue
        if context_files is None:
            return
        build_subtree_context_hook = context_files.build_subtree_context_hook
        file_tool_matcher = context_files.file_tool_matcher
        from praisonaiagents.hooks import HookEvent, HookRegistry
    except (ImportError, AttributeError):
        return

    # Resolve config/flag-declared instruction sources and inject them up front
    # so they sit in the system context alongside the AGENTS.md/CLAUDE.md load.
    already_loaded = ""
    if instructions:
        try:
            already_loaded = context_files.resolve_instruction_sources(instructions)
        except Exception:
            already_loaded = ""
        if already_loaded:
            existing = agent_config.get("backstory") or ""
            block = f"# Project Instructions\n{already_loaded}"
            agent_config["backstory"] = (
                f"{existing}\n\n{block}" if existing else block
            )

    try:
        budget = int(os.environ.get("PRAISON_CONTEXT_BUDGET", "0") or "0")
    except ValueError:
        budget = 0

    try:
        hook = build_subtree_context_hook(already_loaded, max_chars=budget)
        registry = HookRegistry()
        registry.register_function(
            event=HookEvent.AFTER_TOOL,
            func=hook,
            matcher=file_tool_matcher(),
            name="subtree_instruction_injection",
        )
        agent_config["hooks"] = registry
    except Exception:
        return


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
    no_rules: bool = False,
    instructions: Optional[List[str]] = None,
):
    """Run a custom agent definition."""
    output = get_output_controller()
    
    try:
        from praisonaiagents import Agent
        
        # Override model if specified
        if model:
            agent_config["llm"] = model

        # Compose the agent's toolset: frontmatter ``tools:`` (name strings)
        # + explicit --tools/--toolset + auto-discovered project-local
        # .praisonai/tools/*.py callables. Discovery mirrors the default and
        # actions run paths so `--agent` runs honour the same zero-registration
        # convention (gated by PRAISONAI_ALLOW_LOCAL_TOOLS in the safe loader).
        existing_tools = agent_config.get("tools") or []
        if not isinstance(existing_tools, list):
            existing_tools = [existing_tools]
        extra_tools = _resolve_tools_arg(tools, verbose=verbose)
        if toolset:
            from praisonai_code.tool_resolver import resolve_toolsets as _resolve_toolsets
            toolset_names = [t.strip() for t in toolset.split(",") if t.strip()]
            if toolset_names:
                extra_tools.extend(_resolve_toolsets(toolset_names))
        extra_tools.extend(_auto_discover_project_tools(extra_tools, verbose=verbose))
        if extra_tools:
            seen = {id(t) for t in existing_tools}
            merged_extra: list = []
            for t in extra_tools:
                if id(t) in seen:
                    continue
                seen.add(id(t))
                merged_extra.append(t)
            existing_tools = list(existing_tools) + merged_extra
        if existing_tools:
            agent_config["tools"] = existing_tools

        # Offer discovered named agents as delegation targets. The primary
        # agent can then call spawn_subagent(agent_name="researcher", ...) to
        # hand a sub-task to a user-defined .praisonai/agents/*.md agent, which
        # runs under its own model/tools/permissions. An explicit --subagents
        # allow-list wins; otherwise agents marked `mode: subagent` are used.
        _wire_subagent_delegation(agent_config, subagents)
        
        # Map verbosity onto the consolidated ``output=`` preset. A legacy
        # top-level ``verbose=`` kwarg is rejected by the Agent constructor,
        # so ``run --agent <name> --verbose`` would otherwise crash. Only set
        # a preset when the definition did not already supply an explicit
        # ``output``, so a custom agent's own output config still wins.
        if verbose and "output" not in agent_config:
            agent_config["output"] = "verbose"
        
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
        _wire_subtree_context_hook(
            agent_config, no_rules=no_rules, instructions=instructions
        )
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

        succeeded = _run_succeeded(result)
        # A provider content-filter/refusal/length cutoff is a distinct terminal
        # reason recorded by the core; surface it (even when the result is empty)
        # so a blocked run isn't collapsed into a generic ``failed``.
        block_reason = _run_block_reason(agent)
        # Classify a step-limit-truncated run *before* the terminal stream
        # event so a `--output stream-json` consumer never receives a
        # contradictory ``run.result {ok: true}`` ahead of the ``truncated``
        # outcome (exit 2) reported below.
        truncated = succeeded and _run_was_truncated(agent)
        if bridge is not None:
            bridge.emit_run_result(
                result, ok=succeeded and not truncated and not block_reason
            )
        _record_session_usage(session_id or auto_save_name, model, output)
        # A provider block/refusal/truncation wins over a generic empty-result
        # failure so the specific, actionable reason is not masked.
        if block_reason:
            _report_run_blocked(output, result, block_reason)
        if not succeeded:
            _report_run_failure(output)
        if result and not output.is_json_mode:
            print(result)
        # Surface the truncated run distinctly (exit 2 + status "truncated")
        # after the summary is shown, so the wrap-up text is still visible but
        # its incomplete status is not masked as success.
        if truncated:
            _report_run_truncated(output, result)
        output.emit_result(
            message="Agent completed",
            data={"result": str(result) if result else None}
        )
    
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
    no_rules: bool = False,
    instructions: Optional[List[str]] = None,
    approval: Optional[str] = None,
    approve_all_tools: bool = False,
    approval_timeout: Optional[str] = None,
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
        # Verbosity is consolidated into ``output=`` on the Agent constructor;
        # a legacy top-level ``verbose=`` kwarg is rejected.
        "output": "verbose" if verbose else "minimal",
    }
    if model:
        agent_config["llm"] = model

    # Thread the approval backend (e.g. --plan -> PermissionMode.PLAN) into the
    # profiled agent so a read-only planning run stays read-only under
    # --profile instead of silently dropping the deny policy.
    if approval:
        from praisonai_code.cli.features._approval_bridge import resolve_approval_config
        agent_config["approval"] = resolve_approval_config(
            approval, all_tools=approve_all_tools, timeout=approval_timeout,
        )

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
    
    _wire_subtree_context_hook(
        agent_config, no_rules=no_rules, instructions=instructions
    )
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

    # A provider block/refusal/truncation is a distinct terminal reason (exit 2)
    # that wins over a generic empty-result failure, so the specific reason is
    # not masked. Reported after the profile so the timing breakdown is shown.
    _block_reason = _run_block_reason(agent)
    if _block_reason:
        _report_run_blocked(get_output_controller(), response, _block_reason)
    # Honour the same failure contract as the non-profiled paths: an empty
    # agent result is a run failure and must exit non-zero (the report is
    # emitted after the profiling output so the profile is still shown).
    if not _run_succeeded(response):
        _report_run_failure(get_output_controller())
    # A step-limit-truncated run is reported distinctly (exit 2 + status
    # "truncated"), after the profile so the timing breakdown is still shown.
    if _run_was_truncated(agent):
        _report_run_truncated(get_output_controller(), response)
