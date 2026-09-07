"""
Code command group for PraisonAI CLI.

Provides terminal-native code assistant mode.
This command NEVER opens a browser - it runs entirely in the terminal.
"""

from typing import Any, List, Optional

import typer

from praisonai_code.cli.utils.env_utils import scopes_no_plugins

app = typer.Typer(help="Terminal-native code assistant mode")


# Default multi-step tool budget for a *coding* session.
#
# The core Agent defaults (ExecutionConfig.max_iter=20, max_tool_calls_per_turn
# =10) are general-purpose: they suit a question-answering agent with two or
# three tools, and they are deliberately left alone here so no existing library
# user's behaviour changes. They are far too small for a coding agent, whose
# unit of work is read -> edit -> run tests -> read the failure: roughly four
# tool calls per fix attempt, before any orientation (ls/glob/grep) at all. Ten
# calls is "list files, read two files, one grep" — it cannot reach a test run,
# so every non-trivial task truncated mid-way.
#
# 200 is chosen to cover the *tail* rather than the median: agentic coding
# trajectories cluster around 20-40 steps but the hard tasks — the ones a
# benchmark actually measures — run well past 100, and a budget set at the
# median silently truncates exactly those. 200 steps is ~50 edit/verify cycles,
# which comfortably covers a multi-file fix while still bounding a genuinely
# runaway loop. The orthogonal guards are unaffected and still stop a broken
# tool much earlier: the per-tool loop guard, ExecutionConfig.max_execution_time,
# max_budget, and the model's own context limit.
DEFAULT_CODE_MAX_STEPS = 200

# Env fallback so a sandbox/CI runner can set the budget without editing the
# command line (mirrors the --append-system-prompt / PRAISONAI_* convention).
_MAX_STEPS_ENV = "PRAISONAI_CODE_MAX_STEPS"


def resolve_code_max_steps(max_steps=None) -> int:
    """Resolve the coding session's multi-step tool budget.

    Precedence: explicit ``--max-steps`` > ``PRAISONAI_CODE_MAX_STEPS`` >
    :data:`DEFAULT_CODE_MAX_STEPS`. An unparseable or non-positive value falls
    through to the next source rather than failing the run.
    """
    import os as _os

    for candidate in (max_steps, _os.environ.get(_MAX_STEPS_ENV)):
        if candidate is None or candidate == "":
            continue
        try:
            value = int(candidate)
        except (TypeError, ValueError):
            continue
        if value > 0:
            return value
    return DEFAULT_CODE_MAX_STEPS


def build_code_execution_config(max_steps=None):
    """Build the ``ExecutionConfig`` a ``praisonai code`` session runs under.

    Sets *both* budget knobs to the resolved value because the two tool loops
    enforce different ones: the OpenAI-native loop is bounded by ``max_steps``
    (via ``Agent._resolve_max_steps``), while the LiteLLM loop additionally
    counts every tool call in the turn against ``max_tool_calls_per_turn`` —
    which is why a Gemini/Anthropic-routed session stopped after exactly ten
    calls while an OpenAI-routed one ran to twenty. Raising only one leaves the
    other as the real (and invisible) ceiling.

    Returns ``None`` if the core config type cannot be imported, so the agent
    keeps its own defaults rather than failing to start.
    """
    try:
        from praisonaiagents.config import ExecutionConfig
    except Exception:  # noqa: BLE001 — budget is an enhancement, never a hard dep
        try:
            from praisonaiagents.config.feature_configs import ExecutionConfig
        except Exception:  # noqa: BLE001
            return None
    budget = resolve_code_max_steps(max_steps)
    return ExecutionConfig(
        max_steps=budget,
        max_tool_calls_per_turn=budget,
    )


def _install_bypass_approval_backend() -> None:
    """Register an always-approve backend for --no-safe/--dangerously-skip-approval.

    The env vars those flags set are read by the CLI's own tool wiring, but the
    core ``@require_approval`` decorator that gates critical tools resolves its
    decision through the approval registry's backend. Registering
    ``AutoApproveBackend`` there is what actually makes the opt-out flags skip
    approval — the same mechanism ``--plan`` uses to *tighten* the policy, used
    here to loosen it.

    Strictly opt-in: only ever called from the explicit --no-safe /
    --dangerously-skip-approval branch, so the safe-by-default path is
    untouched. Best-effort — a registry failure leaves approvals in place
    (fails closed).
    """
    try:
        from praisonaiagents.approval import get_approval_registry
        from praisonaiagents.approval.backends import AutoApproveBackend

        get_approval_registry().set_backend(AutoApproveBackend())
    except Exception:  # noqa: BLE001 — never fail *open* on a wiring error
        pass


def _clear_bypass_approval_backend() -> None:
    """Undo :func:`_install_bypass_approval_backend` for a safe-mode run.

    Removes the global backend only when it is the ``AutoApproveBackend`` this
    module installs, so a bypass left over from an earlier ``--no-safe`` call in
    the same process (REPL/worker/test) cannot silently keep a later
    safe-by-default session unguarded, while a backend registered by a caller or
    by ``--plan`` is preserved.
    """
    try:
        from praisonaiagents.approval import get_approval_registry
        from praisonaiagents.approval.backends import AutoApproveBackend

        registry = get_approval_registry()
        if isinstance(registry.get_backend(), AutoApproveBackend):
            registry.remove_backend()
    except Exception:  # noqa: BLE001 — best-effort cleanup
        pass


@app.callback(invoke_without_command=True)
@scopes_no_plugins
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
    max_steps: Optional[int] = typer.Option(None, "--max-steps", help=f"Maximum tool-calling steps for this coding session (default: {DEFAULT_CODE_MAX_STEPS}). Env fallback: PRAISONAI_CODE_MAX_STEPS"),
    autonomy: bool = typer.Option(True, "--autonomy/--no-autonomy", help="Enable agent autonomy for complex tasks"),
    append_system_prompt: Optional[str] = typer.Option(None, "--append-system-prompt", help="Append text (or @file) to the system prompt for this invocation only. Env fallback: PRAISONAI_APPEND_SYSTEM_PROMPT"),
    profile: bool = typer.Option(False, "--profile", help="Enable CLI profiling (timing breakdown)"),
    profile_deep: bool = typer.Option(False, "--profile-deep", help="Enable deep profiling (cProfile stats, higher overhead)"),
    print_mode: bool = typer.Option(False, "--print", "-p", help="Headless one-shot: emit a clean machine-readable result (no decorations/profiling) and exit with a status-reflecting code"),
    output: Optional[str] = typer.Option(None, "--output", "-o", help="Output format for -p/--print: json (default) or text"),
    pure: bool = typer.Option(False, "--pure", "--no-plugins", help="Skip discovery/loading of external plugins for this run only (equivalent to PRAISONAI_NO_PLUGINS=1); persisted enable/disable state is unchanged"),
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

    # --pure / --no-plugins: suppression is scoped by the @scopes_no_plugins
    # decorator, which sets PRAISONAI_NO_PLUGINS for the duration of this call
    # and always restores the prior value on return, so it never leaks into a
    # later in-process invocation. Persisted enable/disable state is untouched.

    # --resume is a headless-friendly alias for --session so scripted multi-turn
    # composes as `code --resume <id> -p "follow-up"`. An explicit --session
    # still wins; otherwise the resume id feeds the same continuity path.
    if resume and not session_id:
        session_id = resume

    # Resolve --append-system-prompt (literal text or @file) and export it so
    # every downstream agent-construction path appends it to the system prompt.
    from praisonai_code.cli.utils.append_prompt import apply_append_system_prompt
    apply_append_system_prompt(append_system_prompt)

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

    # Fail closed only on options the headless -p path genuinely cannot honor.
    # --tools/--agent/--plan are wired into the headless branch below (parity
    # with the interactive path) by reusing the existing resolvers, so they are
    # no longer rejected. --no-acp/--no-lsp toggle the resident split-pane TUI's
    # runtime tool servers, which the one-shot headless agent does not spin up,
    # so they remain rejected rather than silently ignored.
    # Options that ARE honored in headless mode: --model, --thinking, --verbose,
    # --workspace, --resume/--session/--continue, --tools, --agent, --plan.
    if print_mode:
        _unsupported = []
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

    # First-run credential gate (issue #4024): route a keyless newcomer to the
    # `setup` wizard (or a detected keyless local endpoint) instead of dead-
    # ending on a raw provider error at LLM call time. Shared with `run`/`chat`
    # and the bare invocation so onboarding is entrypoint-independent. Headless
    # paths (-p/--print, piped stdin) fail fast with the actionable hint and a
    # non-zero exit code rather than prompting. --revert exits above before we
    # reach here, so it never triggers the gate.
    import sys as _sys
    from praisonai_code.llm.credentials import ensure_configured_or_onboard

    # Resolve the agent profile's model BEFORE the gate so onboarding validates
    # (and preserves) the model the session will actually dispatch. Without this,
    # a keyless `code --agent <profile>` with a reachable local endpoint would be
    # handed the detected local model, and the later `if not model` profile
    # override (below) would no longer fire — silently using the wrong model.
    # An explicit --model still wins over the profile's llm.
    _effective_model = model
    if _effective_model is None and agent_profile and agent_profile.get("llm"):
        _effective_model = agent_profile["llm"]

    _headless = bool(print_mode) or not _sys.stdin.isatty()
    _gated_model = ensure_configured_or_onboard(
        model=_effective_model, interactive=not _headless
    )
    # Preserve a user/profile-selected model. Only adopt the gate's return when
    # it changed the effective model (keyless local-first path), so the profile
    # override below still applies for the untouched-model case.
    if _gated_model != _effective_model:
        model = _gated_model
    
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
        # PRAISON_APPROVAL_MODE/PRAISONAI_TOOL_SAFETY are read by the CLI's own
        # tool wiring, but the gate that actually prompts for a critical tool
        # (e.g. acp_execute_command) is the core `@require_approval` decorator,
        # which consults the approval *registry* backend. Without registering a
        # bypass backend the flag left every prompt in place — and a scripted
        # run with no tty answered "no" to each one, so the agent could not run
        # a single command while still exiting 0. Install the same
        # AutoApproveBackend the `--plan` branch already registers below (one
        # mechanism, not a second env var).
        _install_bypass_approval_backend()
    else:
        os.environ["PRAISON_APPROVAL_MODE"] = "prompt"
        # Clear any stale bypass from a previous --no-safe run in the same
        # process (REPL/worker/test). Leaving PRAISONAI_TOOL_SAFETY=off would
        # silently keep later safe-default agents unguarded.
        os.environ.pop("PRAISONAI_TOOL_SAFETY", None)
        # Same reasoning for the registry: a bypass backend installed by an
        # earlier --no-safe run in this process must not survive into a
        # safe-by-default one. Only a backend *we* installed is removed, so a
        # caller-supplied backend is never clobbered.
        _clear_bypass_approval_backend()
    
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
        # Resolve the same --tools / --agent / --plan wiring the interactive
        # path uses, so a headless run is a first-class configurable entrypoint
        # (parity, not a re-implementation). Approvals stay non-interactive:
        # --plan / --agent scope is a *tightening* enforced via a non-interactive
        # backend, never an interactive prompt that would stall a scripted run.
        # NOTE: --tools resolution (which may import a user tools.py) is deferred
        # into _run_print_code so an import-time failure is reported through the
        # same machine-readable JSON/text envelope as any run error, instead of
        # escaping as a raw traceback to a scripted caller.
        headless_approval = None
        if agent_profile:
            permission_config = agent_profile.get("permissions")
            if permission_config:
                from praisonai_code.cli.features._approval_bridge import (
                    resolve_approval_config,
                )
                headless_approval = resolve_approval_config(
                    "console",
                    non_interactive=True,
                    permissions_config=permission_config,
                )
        # --plan overrides any profile scope with the read-only planning mode.
        if plan:
            from praisonai_code.cli.features._approval_bridge import (
                resolve_approval_config,
            )
            headless_approval = resolve_approval_config(
                "plan", non_interactive=True
            )

        _run_print_code(
            prompt=prompt,
            model=model,
            verbose=verbose,
            output_format=output_format or "json",
            thinking_budget=thinking_budget,
            session_id=session_id,
            continue_session=continue_session,
            tools_arg=tools,
            agent_profile=agent_profile,
            approval=headless_approval,
            max_steps=max_steps,
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
            max_steps=max_steps,
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
    # Same coding-sized budget for the interactive session, threaded onto the
    # resident TUI's existing `execution` capability option.
    args.execution = build_code_execution_config(max_steps)

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

    # Import and run the terminal-native interactive mode. The full interactive
    # code session is resident in praisonai-code via the async split-pane TUI, so
    # `pip install praisonai-code` alone yields a working `code` session. The
    # heavier legacy dispatch (`PraisonAI._start_interactive_mode`) adds
    # wrapper-only extras, so use it only when the wrapper is installed and fall
    # back to the resident TUI otherwise.
    from praisonai_code._wrapper_bridge import wrapper_available

    if not wrapper_available():
        _run_resident_code(prompt, args, plan=plan, session_id=session_id)
        return

    from praisonai_code.cli.main import PraisonAI
    
    praison = PraisonAI()
    
    if prompt:
        # Single prompt mode - use _run_chat_mode with code context
        praison._run_chat_mode(prompt, args)
    else:
        # Interactive REPL mode - use _start_interactive_mode
        praison._start_interactive_mode(args)


def _run_resident_code(prompt, args, *, plan=False, session_id=None):
    """Run interactive/one-shot ``code`` on the resident split-pane TUI.

    Used when the ``praisonai`` wrapper is absent so the CLI-first package
    delivers its own flagship interactive coding session with no wrapper
    dependency. Mirrors the ``chat`` command's resident path, mapping the code
    session's args (model/workspace/no-acp/no-lsp/--plan) onto ``AsyncTUIConfig``.
    """
    import os

    from praisonai_code.cli.interactive.async_tui import AsyncTUI, AsyncTUIConfig

    model = getattr(args, "llm", None)
    try:
        from ..configuration.model_resolver import resolve_default_model

        resolved_model = resolve_default_model(model)
    except Exception:
        from praisonai_code.llm.env import DEFAULT_FALLBACK_MODEL

        resolved_model = model or DEFAULT_FALLBACK_MODEL

    # Enforce the resolved permission policy (e.g. --plan / --agent scope) by
    # registering it on the global approval registry the resident TUI reads.
    # Without this the read-only PLAN contract would be silently dropped and
    # mutating tools (write/edit/shell) would stay available. The TUI syncs its
    # PLAN indicator from this backend at construction, so registering here is
    # sufficient — no new AsyncTUIConfig knob is needed for approval wiring.
    agent_approval = getattr(args, "agent_approval", None)
    if agent_approval is not None:
        # resolve_approval_config returns a plain backend for simple modes
        # (e.g. --plan) and an ApprovalConfig wrapper when a profile carries
        # a permissions map; unwrap the wrapper so the registry always holds a
        # concrete backend the TUI can query for PLAN enforcement.
        backend = getattr(agent_approval, "backend", agent_approval)
        try:
            from praisonaiagents.approval import get_approval_registry

            get_approval_registry().set_backend(backend)
        except Exception:
            pass

    tui_config = AsyncTUIConfig(
        model=resolved_model,
        session_id=session_id,
        workspace=os.environ.get("PRAISONAI_WORKSPACE") or os.getcwd(),
        debug=getattr(args, "verbose", False),
        plan_mode=plan,
        enable_acp=not getattr(args, "no_acp", False),
        enable_lsp=not getattr(args, "no_lsp", False),
        execution=getattr(args, "execution", None),
    )

    tui = AsyncTUI(config=tui_config)

    if prompt:
        response = tui.run_single(prompt)
        if response:
            print(response)
        if tui.execution_failed:
            raise typer.Exit(1)
    else:
        tui.run()


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


def _print_result_truncated(agent) -> bool:
    """Whether the headless run stopped by exhausting its step/tool budget.

    Delegates to ``run._run_was_truncated`` so ``code -p`` and ``run`` share one
    definition of "truncated" (the core records ``last_stop_reason ==
    "max_steps"`` on the agent when either tool loop runs out of budget) instead
    of growing a second, drifting guard.
    """
    from praisonai_code.cli.commands.run import _run_was_truncated

    return _run_was_truncated(agent)


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
    tools_arg: Optional[str] = None,
    agent_profile: Optional[dict] = None,
    approval: Optional[Any] = None,
    max_steps: Optional[int] = None,
):
    """Headless one-shot code run with clean stdout and a status exit code.

    Builds the code agent directly (bypassing the decorated interactive path),
    runs the prompt once, and emits a machine-readable envelope
    ``{result, session_id, usage:{in,out,cost}, status}`` to stdout. Exit code
    is 0 on success, 2 when the run was *truncated* by the step/tool budget
    (``status: "truncated"`` — a wrap-up summary, not a finished task), and 1 on
    failure (empty result or raised error), giving scripts/CI/benchmarks a
    reliable signal — parity with ``run --output json``.

    ``tools_arg`` is the raw ``--tools`` string, resolved *inside* this run's
    try/except (via the same ``_resolve_tools_arg``/``ToolResolver`` as the
    interactive/run path) so an import-time failure in a user ``tools.py`` is
    reported through the machine-readable envelope instead of escaping as a raw
    traceback; ``agent_profile`` is a ``--agent`` definition (instructions/llm/
    tools) that overlays the defaults; ``approval`` is the non-interactive
    backend enforcing ``--plan``/profile permission scope. All reuse the
    interactive path's resolvers so headless == interactive for these flags.
    """
    import json
    import os

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
        "instructions": (
            "You are a terminal coding assistant. Inspect the workspace and "
            "use the provided tools for coding tasks. Keep all file operations "
            "inside the configured workspace."
        ),
        # A minimal output preset keeps the agent from printing its own
        # decorations so stdout carries only our envelope.
        "output": "minimal",
    }
    # Give the coding agent a coding-sized step budget. Without this it inherits
    # the general-purpose Agent defaults (20 steps / 10 tool calls per turn) and
    # truncates before it can reach a test run — see DEFAULT_CODE_MAX_STEPS.
    _execution = build_code_execution_config(max_steps)
    if _execution is not None:
        agent_config["execution"] = _execution
    if model:
        agent_config["llm"] = model

    # Overlay a --agent profile's instructions/role/goal/llm so the pinned,
    # least-privilege agent runs headlessly with the same identity it would
    # interactively. Its declarative ``permissions`` are already resolved into
    # the ``approval`` backend by the caller, so they are dropped here.
    profile_tool_names: List[str] = []
    if agent_profile:
        for key in ("instructions", "role", "goal", "backstory"):
            if agent_profile.get(key):
                agent_config[key] = agent_profile[key]
        # An explicit --model still wins over the profile's llm.
        if not model and agent_profile.get("llm"):
            agent_config["llm"] = agent_profile["llm"]
        profile_tools = agent_profile.get("tools")
        if isinstance(profile_tools, (list, tuple)):
            profile_tool_names = [str(t) for t in profile_tools if isinstance(t, str)]

    # Enforce --plan / profile permission scope on a non-interactive backend so
    # honouring the scope is a tightening (deny/ask fails closed), never an
    # interactive prompt that would stall a scripted run.
    if approval is not None:
        agent_config["approval"] = approval

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
    agent = None
    try:
        workspace = os.environ.get("PRAISONAI_WORKSPACE") or os.getcwd()
        merged_tools = _get_headless_code_tools(
            groups=["acp", "edit", "search", "lsp"],
            workspace=workspace,
        )
        # Merge --tools-resolved callables and a --agent profile's named tools
        # onto the default coding toolset so a headless run can add a custom
        # tool (e.g. github) or run under a profile's toolset. Resolution reuses
        # the same ToolResolver as the interactive/run path (CLI == YAML ==
        # Python) and runs inside this try so a failing user tools.py is
        # surfaced via the envelope, not a raw traceback. De-dupe by identity so
        # a repeated default is not doubled.
        additional_tools = []
        if tools_arg:
            from praisonai_code.cli.commands.run import _resolve_tools_arg

            additional_tools.extend(_resolve_tools_arg(tools_arg, verbose=verbose))
        if profile_tool_names:
            from praisonai_code.tool_resolver import ToolResolver

            resolver = ToolResolver()
            for name in profile_tool_names:
                resolved = resolver.resolve(name, instantiate=True)
                if resolved is not None:
                    additional_tools.append(resolved)
        if additional_tools:
            seen = {id(t) for t in merged_tools}
            for tool in additional_tools:
                if id(tool) not in seen:
                    merged_tools.append(tool)
                    seen.add(id(tool))
        agent_config["tools"] = merged_tools
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
    finally:
        try:
            from praisonai_code.cli.features.interactive_tools import cleanup_runtime

            cleanup_runtime()
        except Exception:
            pass

    if status != "error" and not _print_result_succeeded(result):
        status = "failed"
    elif status == "ok" and _print_result_truncated(agent):
        # A step/tool-budget exhaustion still returns a non-empty wrap-up
        # summary, so string-emptiness alone reports a *truncated* run as a
        # completed one. Reuse `run`'s terminal-reason check so both headless
        # surfaces agree, and expose it as a distinct status + exit code.
        status = "truncated"

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
        if status == "truncated":
            typer.echo(
                "Warning: run hit the step/tool-call budget; the output above "
                "is a summary of partial progress, not a completed task. "
                "Re-run with a higher --max-steps.",
                err=True,
            )
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

    if status == "truncated":
        # Exit 2 = incomplete run (mirrors `run`'s truncation contract), distinct
        # from a hard failure (1) and a clean completion (0).
        raise typer.Exit(2)
    if status != "ok":
        raise typer.Exit(1)


def _get_headless_code_tools(*, groups: List[str], workspace: str):
    """Load the same workspace-bound coding tool groups used by the TUI."""
    from praisonai_code.cli.features.interactive_tools import get_interactive_tools

    return get_interactive_tools(groups=groups, workspace=workspace)


def _run_profiled_code(
    prompt: str,
    model: Optional[str] = None,
    verbose: bool = False,
    profile_deep: bool = False,
    thinking_budget: Optional[int] = None,
    max_steps: Optional[int] = None,
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
        # Verbosity is consolidated into ``output=`` on the Agent constructor;
        # a legacy top-level ``verbose=`` kwarg is rejected. A minimal preset
        # keeps profiler stdout clean.
        "output": "verbose" if verbose else "minimal",
    }
    # Same coding-sized budget as the headless/interactive paths, so a profiled
    # single-prompt run does not silently keep the general-purpose core defaults
    # (20 steps / 10 tool calls per turn) and truncate a real coding task.
    _execution = build_code_execution_config(max_steps)
    if _execution is not None:
        agent_config["execution"] = _execution
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
