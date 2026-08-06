"""
Code command group for PraisonAI CLI.

Provides terminal-native code assistant mode.
This command NEVER opens a browser - it runs entirely in the terminal.
"""

from typing import List, Optional

import typer

app = typer.Typer(help="Terminal-native code assistant mode")


@app.callback(invoke_without_command=True)
def code_main(
    ctx: typer.Context,
    prompt: Optional[str] = typer.Argument(None, help="Code task or question"),
    model: Optional[str] = typer.Option(None, "--model", "-m", help="LLM model to use"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output"),
    tools: Optional[str] = typer.Option(None, "--tools", "-t", help="Comma-separated tool names (e.g. web_search,github) or a tools.py file path"),
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w", help="Workspace directory"),
    file: Optional[List[str]] = typer.Option(None, "--file", "-f", help="Attach file(s) to context"),
    no_acp: bool = typer.Option(False, "--no-acp", help="Disable ACP tools (file operations)"),
    no_lsp: bool = typer.Option(False, "--no-lsp", help="Disable LSP tools (code intelligence)"),
    safe_mode: bool = typer.Option(True, "--safe/--no-safe", help="Safe mode (default ON): require approval for file writes and commands"),
    plan: bool = typer.Option(False, "--plan", help="Read-only planning mode: the agent may explore/read/search but every mutating tool is denied (no writes/edits/shell)"),
    dangerously_skip_approval: bool = typer.Option(False, "--dangerously-skip-approval", help="Skip all approval prompts and run dangerous tools unguarded (restores legacy behaviour)"),
    checkpoints: bool = typer.Option(False, "--checkpoints/--no-checkpoints", help="Auto-checkpoint the workspace before each file-mutating turn (enables in-session /undo and /revert)"),
    revert: Optional[str] = typer.Option(None, "--revert", help="Restore the workspace to a prior checkpoint (id, short id, or 'last') and exit"),
    session_id: Optional[str] = typer.Option(None, "--session", "-s", help="Session ID to resume"),
    resume: Optional[str] = typer.Option(None, "--resume", help="Resume a session by id in headless -p mode (alias of --session for scripted multi-turn)"),
    continue_session: bool = typer.Option(False, "--continue", "-c", help="Continue last session"),
    agent: Optional[str] = typer.Option(None, "--agent", "-a", help="Use a named custom agent profile (applies its tools and permission/mode scope)"),
    thinking: Optional[str] = typer.Option(None, "--thinking", help="Reasoning effort (off, minimal, low, medium, high)"),
    autonomy: bool = typer.Option(True, "--autonomy/--no-autonomy", help="Enable agent autonomy for complex tasks"),
    profile: bool = typer.Option(False, "--profile", help="Enable CLI profiling (timing breakdown)"),
    profile_deep: bool = typer.Option(False, "--profile-deep", help="Enable deep profiling (cProfile stats, higher overhead)"),
    print_mode: bool = typer.Option(False, "--print", "-p", help="Headless one-shot: emit a clean machine-readable result (no decorations/profiling) and exit with a status-reflecting code"),
    output: Optional[str] = typer.Option(None, "--output", "-o", help="Output format for -p/--print: json (default) or text"),
):
    """
    Start terminal-native code assistant mode.
    
    This is a terminal-based code assistant with file awareness, diff display,
    and ACP/LSP tools enabled by default. It NEVER opens a browser.
    
    For browser-based code UI, use: praisonai ui code
    
    Examples:
        praisonai code
        praisonai code "Refactor this function"
        praisonai code --model gpt-4o --workspace ./src
        praisonai code "Fix the bug" --file main.py
        praisonai code "What is 2+2?" --profile
        praisonai code -p "Write a parser" --output json  # headless, machine-readable
        praisonai code -p "Write a parser" --output text   # headless, plain text
        praisonai code --resume <id> -p "follow-up"        # scripted multi-turn
    """
    import os
    import argparse

    # Ingest piped stdin so `code` composes in Unix pipelines and CI, e.g.
    #   cat data.json | praisonai code "Write a parser for this shape"
    # The prompt argument comes first, then the piped body. Non-blocking/EOF-safe
    # so an interactive REPL is never stalled.
    from praisonai_code.cli.utils.stdin import resolve_cli_input
    prompt = resolve_cli_input(prompt)

    # --resume is a headless-friendly alias for --session so scripted multi-turn
    # composes as `code --resume <id> -p "follow-up"`. An explicit --session
    # still wins; otherwise the resume id feeds the same continuity path.
    if resume and not session_id:
        session_id = resume

    # Validate --thinking up front so an unknown value fails closed before any
    # work is done (consistent with MODE_RULES validation on custom agents).
    from praisonai_code.cli.features.thinking import thinking_to_budget
    try:
        thinking_budget = thinking_to_budget(thinking)
    except ValueError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(1)

    # Headless output format. Default to json when -p/--print is set so the
    # flagship command reaches parity with `run --output json`/`chat --json`.
    # Validate up front so an unknown value fails closed before any work.
    output_format = (output or ("json" if print_mode else None))
    if output_format is not None and output_format not in ("json", "text"):
        typer.echo(
            f"Error: unknown --output '{output_format}' (expected: json, text)",
            err=True,
        )
        raise typer.Exit(1)
    # --output only shapes the headless -p path; a bare --output without -p is a
    # no-op today, so require -p to keep the contract explicit and scriptable.
    if output is not None and not print_mode:
        typer.echo("Error: --output requires -p/--print", err=True)
        raise typer.Exit(1)
    if print_mode and not prompt:
        typer.echo("Error: -p/--print requires a task prompt", err=True)
        raise typer.Exit(1)

    # Fail closed on options the headless -p path cannot honor. The full
    # ACP/LSP tool wiring and named-profile permission scope live in the
    # interactive path; silently dropping them (as a bare early-return would)
    # is worse than an explicit error, since tool/profile-dependent tasks would
    # run without the tools or scope the caller asked for. Reject rather than
    # re-implement that heavy wiring here (keeps the command lightweight).
    # Options that ARE honored in headless mode: --model, --thinking, --verbose,
    # --workspace, --resume/--session/--continue.
    if print_mode:
        _unsupported = []
        if tools:
            _unsupported.append("--tools")
        if agent:
            _unsupported.append("--agent")
        if plan:
            _unsupported.append("--plan")
        if no_acp:
            _unsupported.append("--no-acp")
        if no_lsp:
            _unsupported.append("--no-lsp")
        if _unsupported:
            typer.echo(
                "Error: -p/--print does not support "
                + ", ".join(_unsupported)
                + " (headless mode runs a minimal code agent; use interactive "
                "mode for tool/profile configuration)",
                err=True,
            )
            raise typer.Exit(1)

    # Resolve a named agent profile (tools + permission/mode scope). The profile
    # reuses the same custom-definitions loader as `praisonai run --agent`, so a
    # profile defined once in .praisonai/agents/<name>.md behaves identically
    # across `code`, `run`, and the Python Agent(...) constructor.
    agent_profile = None
    if agent:
        from praisonai_code.cli.features.custom_definitions import load_agent_from_name
        agent_profile = load_agent_from_name(agent)
        if not agent_profile:
            typer.echo(f"Error: Agent '{agent}' not found", err=True)
            raise typer.Exit(1)

    # Set workspace if provided
    if workspace:
        os.environ["PRAISONAI_WORKSPACE"] = workspace

    # --revert: restore the workspace to a prior checkpoint and exit before
    # starting a session. Reuses the existing CheckpointsHandler so the same
    # 'last'/short-id/prefix resolution as `praisonai checkpoint restore`
    # applies. This is a one-shot CLI path, not the interactive /revert.
    if revert is not None:
        _revert_workspace(revert, workspace or os.getcwd(), verbose)
        return

    # --checkpoints opts the session into turn-aware auto-checkpointing,
    # surfaced to the interactive loop via the env override the session
    # checkpoint manager reads. Default off keeps zero overhead.
    if checkpoints:
        os.environ["PRAISONAI_CHECKPOINTS"] = "on"

    # Enable code-specific environment
    os.environ["PRAISONAI_CODE_MODE"] = "true"
    
    # Set approval mode based on --safe flag.
    # Safe-by-default: dangerous tools (shell exec, file writes) are gated
    # behind an interactive approval prompt unless the user explicitly opts
    # out with --no-safe or --dangerously-skip-approval. The latter also sets
    # PRAISONAI_TOOL_SAFETY=off so the core runtime skips its safe-by-default
    # ask path (see Agent.__init__ approval handling).
    # --plan selects the read-only planning mode: the agent may explore/read but
    # every mutating tool (write/edit/shell/exec) is denied. It is the opposite
    # of skipping approval, so reject the contradictory combination up front
    # rather than silently letting one win.
    if plan and (dangerously_skip_approval or not safe_mode):
        typer.echo(
            "Error: --plan (read-only) cannot be combined with "
            "--no-safe/--dangerously-skip-approval",
            err=True,
        )
        raise typer.Exit(1)

    if dangerously_skip_approval or not safe_mode:
        os.environ["PRAISON_APPROVAL_MODE"] = "auto"
        os.environ["PRAISONAI_TOOL_SAFETY"] = "off"
    else:
        os.environ["PRAISON_APPROVAL_MODE"] = "prompt"
        # Clear any stale bypass from a previous --no-safe run in the same
        # process (REPL/worker/test). Leaving PRAISONAI_TOOL_SAFETY=off would
        # silently keep later safe-default agents unguarded.
        os.environ.pop("PRAISONAI_TOOL_SAFETY", None)
    
    # Headless one-shot: emit a clean, machine-readable envelope and exit with a
    # status-reflecting code. Routes around the decorated interactive chat path
    # (which prints `Chat mode:`/`Prompt:` diagnostics + a profiling block and
    # always returns None) so stdout carries only the result envelope. Reuses
    # the existing token collector + cost tracker for usage, so no new Agent
    # params or wrapper wiring are introduced (parity with `run --output json`).
    #
    # NOTE: this must run BEFORE the profiling branch below. Profiling prints a
    # human-oriented report and always exits 0, which would violate the -p
    # machine-readable contract if it won the race; and the two are mutually
    # exclusive intents (diagnostic vs scriptable). Reject the combination and
    # honor -p when both are requested.
    if print_mode and prompt:
        if profile or profile_deep:
            typer.echo(
                "Error: -p/--print (headless machine-readable) cannot be "
                "combined with --profile/--profile-deep",
                err=True,
            )
            raise typer.Exit(1)
        _run_print_code(
            prompt=prompt,
            model=model,
            verbose=verbose,
            output_format=output_format or "json",
            thinking_budget=thinking_budget,
            session_id=session_id,
            continue_session=continue_session,
        )
        return

    # Handle profiling for single prompt mode (non-headless). Runs after the
    # -p branch above so headless output always wins the machine-readable path.
    if prompt and (profile or profile_deep):
        _run_profiled_code(
            prompt=prompt,
            model=model,
            verbose=verbose,
            profile_deep=profile_deep,
            thinking_budget=thinking_budget,
        )
        return

    # Warn if profiling requested without prompt (REPL mode doesn't support profiling)
    if (profile or profile_deep) and not prompt:
        typer.echo("⚠️  Profiling is only supported for single prompt mode.", err=True)
        typer.echo("   Use: praisonai code \"your prompt\" --profile", err=True)
    
    # Build args namespace for _start_interactive_mode
    args = argparse.Namespace()
    args.llm = model
    args.verbose = verbose
    args.tools = tools
    args.no_acp = no_acp
    args.no_lsp = no_lsp
    args.resume_session = session_id if session_id else ('last' if continue_session else None)
    # Reasoning effort (mapped to the core thinking_budget) and named agent
    # profile (tools + permission/mode scope), consumed when the agent is built.
    args.thinking_budget = thinking_budget
    args.agent_profile = agent_profile

    # Resolve the named profile's permission/mode scope into an approval config
    # so the code session runs least-privilege (e.g. `--agent plan` is rejected
    # for write/edit/shell). Reuses the same engine as `praisonai run --agent`.
    args.agent_approval = None
    if agent_profile:
        permission_config = agent_profile.get("permissions")
        if permission_config:
            from praisonai_code.cli.features._approval_bridge import resolve_approval_config
            has_ask_rules = any(
                str(action).strip().lower() == "ask"
                for action in permission_config.values()
            )
            args.agent_approval = resolve_approval_config(
                "console",
                non_interactive=not has_ask_rules,
                permissions_config=permission_config,
            )
        # Apply the profile's model unless the user overrode it with --model.
        if not model and agent_profile.get("llm"):
            args.llm = agent_profile["llm"]

    # --plan overrides any profile scope with the read-only planning mode,
    # threading PermissionMode.PLAN through the existing approval config so the
    # code session denies every mutating tool. Non-interactive: PLAN is a hard
    # read-only policy, not an ask-per-call prompt.
    if plan:
        from praisonai_code.cli.features._approval_bridge import resolve_approval_config
        args.agent_approval = resolve_approval_config(
            "plan", non_interactive=True
        )

    # Import and run the terminal-native interactive mode
    from praisonai_code._wrapper_bridge import wrapper_available

    if not wrapper_available():
        typer.echo(
            "Error: code requires the praisonai wrapper. "
            "Install the full wrapper: pip install praisonai",
            err=True,
        )
        raise typer.Exit(1)

    from praisonai_code.cli.main import PraisonAI
    
    praison = PraisonAI()
    
    if prompt:
        # Single prompt mode - use _run_chat_mode with code context
        praison._run_chat_mode(prompt, args)
    else:
        # Interactive REPL mode - use _start_interactive_mode
        praison._start_interactive_mode(args)


def _print_result_succeeded(result) -> bool:
    """Whether a headless code result represents a genuine success.

    Mirrors ``run._run_succeeded``: ``Agent.start`` collapses failures (swallowed
    LLM/auth error, guardrail block, tool failure, ``max_iter`` without
    completion) to a falsy result, while a real answer is a non-empty string.
    A falsy result is a failure so ``code -p`` exits non-zero.
    """
    if result is None:
        return False
    if isinstance(result, str):
        return bool(result.strip())
    return True


def _collect_print_usage(model: Optional[str]) -> dict:
    """Return this run's ``{in, out, cost}`` usage from the token collector.

    Reuses the same collector + pricing path as ``run``'s session accounting so
    the headless envelope reports real token/cost figures without any new
    plumbing. Best-effort: any failure yields a zeroed usage block so the
    envelope shape is stable for scripts.
    """
    usage = {"in": 0, "out": 0, "cost": 0.0}
    try:
        from praisonaiagents.telemetry.token_collector import get_token_collector

        summary = get_token_collector().get_session_summary()
    except Exception:
        return usage

    totals = (summary or {}).get("total_metrics") or {}
    usage["in"] = int(totals.get("input_tokens", 0) or 0)
    usage["out"] = int(totals.get("output_tokens", 0) or 0)

    try:
        from ..features.cost_tracker import get_pricing

        by_model = (summary or {}).get("by_model") or {}
        if by_model:
            cost = 0.0
            for model_name, metrics in by_model.items():
                pricing = get_pricing(model_name or model or "default")
                cost += pricing.calculate_cost(
                    int((metrics or {}).get("input_tokens", 0) or 0),
                    int((metrics or {}).get("output_tokens", 0) or 0),
                )
            usage["cost"] = cost
        else:
            pricing = get_pricing(model or "default")
            usage["cost"] = pricing.calculate_cost(usage["in"], usage["out"])
    except Exception:
        usage["cost"] = 0.0

    return usage


def _run_print_code(
    prompt: str,
    model: Optional[str] = None,
    verbose: bool = False,
    output_format: str = "json",
    thinking_budget: Optional[int] = None,
    session_id: Optional[str] = None,
    continue_session: bool = False,
):
    """Headless one-shot code run with clean stdout and a status exit code.

    Builds the code agent directly (bypassing the decorated interactive path),
    runs the prompt once, and emits a machine-readable envelope
    ``{result, session_id, usage:{in,out,cost}, status}`` to stdout. Exit code
    is 0 on success and 1 on failure (empty result or raised error), giving
    scripts/CI/benchmarks a reliable signal — parity with ``run --output json``.
    """
    import json

    try:
        from praisonaiagents import Agent
    except ImportError:
        typer.echo("Error: praisonaiagents not installed", err=True)
        raise typer.Exit(1)

    # Reset per-run token accounting so the emitted usage reflects only this
    # invocation, not any accumulated state in a reused process (REPL/test).
    try:
        from praisonaiagents.telemetry.token_collector import get_token_collector

        get_token_collector().reset()
    except Exception:
        pass

    # Resolve/continue a session id so --resume/--continue compose with -p for
    # scripted multi-turn. Best-effort: continuity is layered via the shared
    # CLI helpers, mirroring the run path, and never blocks a headless run.
    resolved_session = session_id
    if resolved_session is None and continue_session:
        try:
            from ..state.project_sessions import find_last_session

            resolved_session = find_last_session()
        except Exception:
            resolved_session = None

    agent_config = {
        "name": "CodeAgent",
        "role": "Code Assistant",
        "goal": "Help with coding tasks",
        "verbose": verbose,
        # A minimal output preset keeps the agent from printing its own
        # decorations so stdout carries only our envelope.
        "output": "minimal",
    }
    if model:
        agent_config["llm"] = model

    memory_cfg = None
    if resolved_session:
        try:
            from ..state.project_sessions import build_cli_memory_config

            memory_cfg = build_cli_memory_config(
                session_id=resolved_session, auto_save=resolved_session
            )
        except Exception:
            memory_cfg = None
    if memory_cfg is not None:
        agent_config["memory"] = memory_cfg

    status = "ok"
    result = None
    error_message = None
    try:
        agent = Agent(**agent_config)
        if thinking_budget is not None:
            agent.thinking_budget = thinking_budget
        if resolved_session:
            try:
                from ..state.project_sessions import apply_cli_session_continuity

                apply_cli_session_continuity(
                    agent, resolved_session, auto_save=resolved_session
                )
            except Exception:
                pass
        result = agent.start(prompt)
    except Exception as exc:  # noqa: BLE001 - surface any failure via exit code
        status = "error"
        error_message = str(exc)

    if status != "error" and not _print_result_succeeded(result):
        status = "failed"

    usage = _collect_print_usage(model)

    if resolved_session:
        try:
            from ..state.project_sessions import accumulate_session_usage

            accumulate_session_usage(resolved_session, model=model)
        except Exception:
            pass

    if output_format == "text":
        # Clean text mode: the result on stdout, errors on stderr, status via
        # exit code — nothing else — so it pipes cleanly.
        if result:
            print(result)
        if error_message:
            typer.echo(f"Error: {error_message}", err=True)
    else:
        envelope = {
            "result": str(result) if result else None,
            "session_id": resolved_session,
            "usage": usage,
            "status": status,
        }
        if error_message:
            envelope["error"] = error_message
        print(json.dumps(envelope))

    if status != "ok":
        raise typer.Exit(1)


def _run_profiled_code(
    prompt: str,
    model: Optional[str] = None,
    verbose: bool = False,
    profile_deep: bool = False,
    thinking_budget: Optional[int] = None,
):
    """Run code assistant with profiling enabled."""
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
        "name": "CodeAgent",
        "role": "Code Assistant",
        "goal": "Help with coding tasks",
        "verbose": verbose,
    }
    if model:
        agent_config["llm"] = model
    
    agent = Agent(**agent_config)
    # thinking_budget is set post-construction via the property setter (the
    # Agent constructor does not accept it as a keyword argument).
    if thinking_budget is not None:
        agent.thinking_budget = thinking_budget
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


def _revert_workspace(ref: str, workspace: str, verbose: bool = False) -> None:
    """Restore the workspace to a checkpoint (one-shot ``code --revert``).

    Resolves ``ref`` ('last'/short id/prefix) the same way
    ``praisonai checkpoint restore`` does, previews the diff, then restores.
    """
    import asyncio

    from praisonai_code.cli.commands.checkpoint import _resolve_checkpoint_id
    from praisonai_code.cli.features.checkpoints import CheckpointsHandler

    # Honor a configured checkpoints.storage_dir so this one-shot restore reads
    # from the same store the interactive session writes to.
    storage_dir = None
    try:
        from ..configuration.resolver import resolve_config
        section = (resolve_config().extra or {}).get("checkpoints", {})
        if isinstance(section, dict):
            storage_dir = section.get("storage_dir")
    except Exception:
        storage_dir = None

    handler = CheckpointsHandler(
        workspace_dir=workspace, verbose=verbose, storage_dir=storage_dir
    )

    async def _run() -> bool:
        resolved = await _resolve_checkpoint_id(handler, ref)
        if resolved is None:
            handler._print_error(f"No checkpoint found for: {ref}")
            return False
        # Preview what restoring will change before applying it.
        await handler.diff(resolved, None)
        return await handler.restore(resolved)

    if not asyncio.run(_run()):
        raise typer.Exit(1)
