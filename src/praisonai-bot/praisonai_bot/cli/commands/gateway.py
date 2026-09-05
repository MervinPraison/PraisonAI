"""
Gateway command group for PraisonAI CLI.

Provides commands for managing the WebSocket gateway with multi-bot support.
"""

import sys
from typing import Optional

import typer

app = typer.Typer(
    help="Manage the PraisonAI Gateway server",
    no_args_is_help=True,
)


def _resolve_gateway_config_path(explicit: Optional[str]) -> Optional[str]:
    """Resolve one canonical gateway config path across all gateway commands.

    Precedence (mirrors ``bot start`` so ``onboard``/``start``/``doctor`` cannot
    drift apart, #3880):

    1. An explicit ``--config`` value the operator passed (any non-sentinel).
    2. ``./bot.yaml`` in the working dir (back-compat for checked-in configs).
    3. ``~/.praisonai/bot.yaml`` (or ``PRAISONAI_BOT_CONFIG``) — where
       ``praisonai onboard`` writes.
    4. ``./gateway.yaml`` — accepted alias for backward compatibility.

    Returns the resolved path, or ``None`` when nothing was passed and no
    onboarded/legacy config exists (callers turn this into a next-step hint
    rather than silently starting channel-less).
    """
    import os

    if explicit:
        return explicit

    # Prefer the canonical ``praisonai_code`` resolver when co-installed so the
    # gateway CLI agrees with ``bot start``/``onboard`` on every override path.
    try:
        from praisonai_bot._code_bridge import import_code_module

        resolve_bot_config_path = import_code_module(
            "praisonai_code.cli._paths"
        ).resolve_bot_config_path
        resolved = resolve_bot_config_path("bot.yaml")
        if resolved and os.path.exists(resolved):
            return resolved
    except Exception:  # pragma: no cover — praisonai-code not installed
        # ``praisonai-code`` is an OPTIONAL dependency of praisonai-bot, so its
        # absence must NOT hide an onboarded ``~/.praisonai/bot.yaml`` (which is
        # a plain filesystem convention, not owned by praisonai-code). Fall
        # through to the inlined home discovery below (#3880, Greptile P1).
        pass

    # Inlined equivalent of ``resolve_bot_config_path`` so home discovery works
    # even without praisonai-code: cwd ``./bot.yaml`` → ``PRAISONAI_BOT_CONFIG``
    # / ``~/.praisonai/bot.yaml``.
    if os.path.exists("bot.yaml"):
        return "bot.yaml"

    home_cfg = os.environ.get("PRAISONAI_BOT_CONFIG")
    if not home_cfg:
        home = os.environ.get("PRAISONAI_HOME")
        home_dir = (
            os.path.expanduser(home) if home
            else os.path.join(os.path.expanduser("~"), ".praisonai")
        )
        home_cfg = os.path.join(home_dir, "bot.yaml")
    else:
        home_cfg = os.path.expanduser(home_cfg)
    if os.path.exists(home_cfg):
        return home_cfg

    if os.path.exists("gateway.yaml"):
        return "gateway.yaml"

    return None


def _resolve_doctor_config(config: str) -> str:
    """Resolve the config for doctor/test/status/send/channels (#3880).

    These commands default ``--config`` to the ``"gateway.yaml"`` sentinel. When
    the operator did not override it, discover the onboarded config the same way
    ``start`` does (``./bot.yaml`` → ``~/.praisonai/bot.yaml`` → ``gateway.yaml``
    alias) so they agree with ``onboard``/``start`` instead of looking at a file
    onboarding never wrote. An explicit ``--config`` always wins; when nothing
    is discovered the ``"gateway.yaml"`` default is preserved so the existing
    "config not found" message keeps working.
    """
    if config and config != "gateway.yaml":
        return config
    resolved = _resolve_gateway_config_path(None)
    return resolved if resolved else config


def _ensure_config_current(config_path: str) -> None:
    """Validate + forward-migrate a gateway config at start time (#3880).

    ``gateway start`` previously applied an unversioned config without ever
    running the version check/migration that ``doctor`` does, so an out-of-date
    config ran silently until the operator happened to run ``doctor``. This
    runs the SAME canonical check ``doctor`` uses so ``start`` and ``doctor``
    never disagree: an out-of-date config is migrated forward in place; a config
    written by a newer build (or with a malformed stamp) refuses to start with
    an actionable hint rather than being downgraded.
    """
    result = _check_config_version(config_path)
    if result is None:
        return
    # A ``str`` means the config is newer than this build / malformed: refuse to
    # start rather than downgrade it silently.
    if isinstance(result, str):
        print(f"config: {result}")
        raise typer.Exit(78)
    reasons, from_version, to_version = result
    applied = _repair_config_version(config_path)
    for reason in applied:
        print(f"config: {reason}")
    print(f"config: migrated config_version {from_version} -> {to_version}")


@app.command("start")
def gateway_start(
    host: str = typer.Option("127.0.0.1", "--host", help="Host to bind to"),
    port: Optional[int] = typer.Option(None, "--port", help="Port to listen on"),
    agents: Optional[str] = typer.Option(None, "--agents", help="Path to agent configuration file"),
    config: Optional[str] = typer.Option(None, "--config", help="Path to gateway.yaml for multi-bot mode"),
    preflight: bool = typer.Option(
        True,
        "--preflight/--no-preflight",
        help="Validate channel credentials before starting. A channel with a bad "
        "token is reported and skipped (parked degraded, auto-recovers); the "
        "gateway still serves every healthy channel. Use --no-preflight to skip "
        "probing entirely, or --strict-preflight to abort on any bad token",
    ),
    strict_preflight: Optional[bool] = typer.Option(
        None,
        "--strict-preflight/--no-strict-preflight",
        help="Fail fast and abort the whole gateway if ANY channel credential is "
        "bad, instead of isolating that one channel as degraded. Defaults to the "
        "config's gateway.preflight.strict (off) (#4862)",
    ),
    strict_tools: bool = typer.Option(
        True,
        "--strict-tools/--no-strict-tools",
        help="Fail fast if any tool named in the config cannot be resolved. "
        "Use --no-strict-tools to skip unresolved tools and start anyway (#3553)",
    ),
    verify_turn: Optional[bool] = typer.Option(
        None,
        "--verify-turn/--no-verify-turn",
        help="Run one real agent turn before serving so a missing/invalid model "
        "credential fails at startup, not on the first user message. Defaults to "
        "the config's gateway.preflight.verify_turn (on). Use --no-verify-turn to "
        "skip in constrained/offline environments (#4042)",
    ),
    openai_api: bool = typer.Option(
        False,
        "--openai-api",
        help="Serve OpenAI-compatible endpoints (/v1/chat/completions, "
        "/v1/responses, /v1/models) backed by the gateway's live agents",
    ),
    mcp: bool = typer.Option(
        False,
        "--mcp",
        help="Serve an MCP JSON-RPC endpoint (/mcp) exposing the gateway's agents",
    ),
    drain_timeout: Optional[float] = typer.Option(
        None, "--drain-timeout",
        help="Seconds to wait for in-flight agent turns to finish on shutdown "
        "(0 disables; #2375)",
    ),
    max_concurrent_runs: Optional[int] = typer.Option(
        None, "--max-concurrent-runs",
        help="Gateway-wide ceiling on simultaneously-running agent turns "
        "(0 disables; #2454)",
    ),
    queue_depth: Optional[int] = typer.Option(
        None, "--queue-depth",
        help="Bounded wait queue depth when at the concurrency ceiling (#2454)",
    ),
    overflow_policy: Optional[str] = typer.Option(
        None, "--overflow-policy",
        help="Behaviour when the wait queue is full: reject | queue | shed_oldest "
        "(default: reject; #2454)",
    ),
    reliability: Optional[str] = typer.Option(
        None, "--reliability",
        help="Named reliability posture composing drain + admission in one switch: "
        "production | default | off (#2531)",
    ),
    identity_store: Optional[str] = typer.Option(
        None, "--identity-store",
        help="Enable cross-platform conversation continuity: path to the identity "
        "link-map JSON (default ~/.praisonai/identity.json). Paired/linked users "
        "share one session + memory across channels (#3020)",
    ),
    scale_to_zero: bool = typer.Option(
        False, "--scale-to-zero",
        help="Quiesce the gateway when idle for --idle-minutes (scale-to-zero; #3021)",
    ),
    idle_minutes: Optional[float] = typer.Option(
        None, "--idle-minutes",
        help="Minutes of no inbound / in-flight work before quiescing (#3021)",
    ),
    drain_marker: Optional[str] = typer.Option(
        None, "--drain-marker",
        help="Path to watch for an epoch-aware external drain marker file (#3021)",
    ),
    watchdog: bool = typer.Option(
        False, "--watchdog",
        help="Enable the event-loop liveness watchdog: an OS-thread backstop "
        "that dumps stacks and hard-exits (restart code 75) if the loop freezes, "
        "so the supervisor relaunches the process (#3410)",
    ),
    watchdog_timeout: Optional[float] = typer.Option(
        None, "--watchdog-timeout",
        help="Seconds the event loop may stall before the watchdog trips a "
        "restart (default ~15s = 5s x 3 strikes; #3410)",
    ),
):
    """Start the gateway server.

    When ``--config`` is omitted, the onboarded config is auto-discovered
    (``./bot.yaml`` → ``~/.praisonai/bot.yaml`` → ``gateway.yaml`` alias) so the
    happy path after ``praisonai onboard`` starts WITH channels instead of a
    silent channel-less no-op. Its ``config_version`` is validated and migrated
    forward the same way ``gateway doctor`` does before binding. Pass
    ``--agents <path>`` for single-agent mode (no channel config).

    Examples:
        praisonai gateway start
        praisonai gateway start --config gateway.yaml
        praisonai gateway start --agents agents.yaml --port 9000
        praisonai gateway start --config gateway.yaml --no-preflight
        praisonai gateway start --config gateway.yaml --openai-api --mcp
        praisonai gateway start --config gateway.yaml --reliability production
        praisonai gateway start --config gateway.yaml --max-concurrent-runs 8 --queue-depth 32
        GATEWAY_PORT=9000 praisonai gateway start
    """
    import os
    from ..features.gateway import GatewayHandler

    # Check for GATEWAY_PORT environment variable if port not specified
    if port is None:
        try:
            port = int(os.environ.get("GATEWAY_PORT", "8765"))
        except ValueError:
            port = 8765

    # Resolve one canonical gateway config shared with onboard/doctor (#3880).
    # Without this, no --config silently started WebSocket-only with NO channels
    # while doctor looked at a different file. Only auto-discover when the
    # operator did not pass --agents (single-agent mode has no channel config).
    if config is None and agents is None:
        config = _resolve_gateway_config_path(None)
        if config is None:
            print(
                "No gateway config found. Run 'praisonai onboard' to create one, "
                "or pass --config <path> (or --agents <path> for single-agent mode)."
            )
            raise typer.Exit(78)
        print(f"Using gateway config: {config}")

    # Validate + forward-migrate the config version BEFORE binding so start and
    # doctor never disagree about whether a config is current (#3880).
    if config and os.path.exists(config):
        _ensure_config_current(config)

    # Pre-flight: validate channel credentials before launch so bad/expired
    # tokens fail fast with a precise per-channel reason instead of entering a
    # silent reconnect loop (#2426). Only runs in multi-bot config mode.
    if preflight and config and os.path.exists(config):
        import asyncio

        # _probe_channels() loads ~/.praisonai/.env before resolving ${VAR}
        # tokens, mirroring GatewayHandler.start() so valid env-file tokens
        # are not falsely rejected (#2426).
        channels = _load_channels(config)
        if channels:
            # Resolve strict mode: the CLI flag overrides, else fall back to the
            # config's gateway.preflight.strict (default off; #4862).
            strict = _resolve_strict_preflight(config)
            if strict_preflight is not None:
                strict = strict_preflight

            results = asyncio.run(_probe_channels(channels))
            all_ok = _render_probe_results(results)
            if not all_ok:
                # Partition the failures. An SSL certificate-verify failure
                # (corporate proxy / MITM) is NOT a credential problem — the same
                # token connects fine at runtime (#2845) — so SSL-only failures
                # always warn-and-continue.
                healthy = [
                    name for name, r in results.items()
                    if getattr(r, "ok", False)
                ]
                cred_failures = [
                    name for name, r in results.items()
                    if not getattr(r, "ok", False) and not _is_ssl_error(r)
                ]
                # The isolate-vs-abort-vs-ssl decision is a pure function so it
                # can be unit-tested without typer (#4862).
                action = _classify_preflight_action(healthy, cred_failures, strict)
                if action == "abort":
                    # A bad/expired token isolates ONLY that channel: the runtime
                    # parks it in ChannelState.CREDENTIAL_UNAVAILABLE (queryable
                    # via gateway status/doctor, auto-recovers on hot-reload)
                    # while every healthy channel keeps serving (#4862). Fail
                    # closed only when the operator opted into strict mode, or
                    # when NO channel is serviceable (nothing left to serve).
                    why = (
                        "--strict-preflight set"
                        if strict and healthy
                        else "no serviceable channel"
                    )
                    print(
                        f"\nPre-flight check failed — aborting start ({why}). "
                        "Fix the channel credentials above, or pass "
                        "--no-preflight to skip / --no-strict-preflight to "
                        "isolate the degraded channel and serve the rest."
                    )
                    raise typer.Exit(1)
                elif action == "isolate":
                    print(
                        f"\nPre-flight: {len(healthy)} channel(s) OK; skipping "
                        f"{', '.join(cred_failures)} as configured-unavailable "
                        "(auto-recovers when the credential is fixed). "
                        "See `gateway status`."
                    )
                else:
                    print(
                        "\nPre-flight found SSL certificate-verify failures only "
                        "(likely a proxy/MITM network). Tokens may still be valid — "
                        "continuing start. Set SSL_CERT_FILE / REQUESTS_CA_BUNDLE / "
                        "PRAISONAI_SSL_CA_BUNDLE to your corporate CA, or pass "
                        "--no-preflight to skip this check."
                    )

    # Tool pre-flight: a tool named in the config that cannot be resolved (a
    # typo, an uninstalled optional package, or a gated local tools.py) is
    # otherwise silently skipped — the bot starts quietly under-powered with
    # only a log warning an operator never sees (#3553). Mirror the credential
    # pre-flight: fail fast by default with a per-name reason + fix hint, or
    # warn-and-continue under --no-strict-tools.
    if config and os.path.exists(config):
        _preflight_tools(config, strict_tools=strict_tools)

    # Turn pre-flight: verify one real agent turn so a missing/invalid model
    # credential fails HERE (at start), not silently on the first user message
    # (#4042). The channel + tool probes above prove wiring, never a model
    # round-trip. Default on via config (gateway.preflight.verify_turn); the
    # --verify-turn/--no-verify-turn flag overrides for constrained/offline use.
    #
    # This is governed by its own toggle, NOT the channel `preflight` flag: an
    # operator running `--no-preflight --verify-turn` still wants the model
    # round-trip, so skipping the channel probes must not silently suppress the
    # requested turn check.
    if config and os.path.exists(config):
        import asyncio

        enabled, prompt = _resolve_verify_turn(config)
        if verify_turn is not None:
            enabled = verify_turn
        channels = _load_channels(config)
        if enabled and channels:
            ok, detail = asyncio.run(_verify_turn_preflight(config, prompt=prompt))
            if ok:
                print(f"Turn pre-flight OK — agent replied to '{prompt}'.")
            else:
                print(
                    f"\nTurn pre-flight failed — the agent did not produce a reply: "
                    f"{detail}\nCheck the model/provider credentials for this agent, "
                    "or pass --no-verify-turn to skip this check."
                )
                raise typer.Exit(1)

    handler = GatewayHandler()
    # Pass True only when the flag is set so an unset flag does not override a
    # YAML ``gateway.api.*`` value (None = "fall back to config"). The same
    # None-means-fall-back-to-YAML rule applies to the reliability/admission/
    # idle/drain/identity flags below, so operators get one canonical, fully
    # discoverable ``gateway start --help`` surface (#3161).
    #
    # Propagate the supervisor-friendly exit code (#2437, #3160): Typer ignores
    # a plain returned int, so a fatal-config (78) / transient (75) / clean (0)
    # result must be surfaced via ``typer.Exit`` — otherwise the installed
    # daemon (which runs ``python -m praisonai_bot gateway start``) always exits
    # 0, and the generated units' Restart=on-failure / RestartPreventExitStatus
    # / KeepAlive.SuccessfulExit directives never see the real code.
    code = handler.start(
        host=host,
        port=port,
        agent_file=agents,
        config_file=config,
        openai_api=True if openai_api else None,
        mcp=True if mcp else None,
        drain_timeout=drain_timeout,
        max_concurrent_runs=max_concurrent_runs,
        queue_depth=queue_depth,
        overflow_policy=overflow_policy,
        reliability=reliability,
        identity_store=identity_store,
        scale_to_zero=True if scale_to_zero else None,
        idle_minutes=idle_minutes,
        drain_marker=drain_marker,
        watchdog=True if watchdog else None,
        watchdog_timeout=watchdog_timeout,
    )
    raise typer.Exit(code if isinstance(code, int) else 0)


@app.command("stop")
def gateway_stop(
    host: str = typer.Option("127.0.0.1", "--host", help="Gateway host"),
    port: Optional[int] = typer.Option(None, "--port", help="Gateway port"),
    force: bool = typer.Option(False, "--force", help="Force stop (kill process)"),
):
    """Stop a running gateway instance.

    Examples:
        praisonai gateway stop
        praisonai gateway stop --port 9000
        praisonai gateway stop --force
    """
    import os
    from ..features.gateway import GatewayHandler
    from ..output.console import get_output_controller
    
    # Check for GATEWAY_PORT environment variable if port not specified
    if port is None:
        try:
            port = int(os.environ.get("GATEWAY_PORT", "8765"))
        except ValueError:
            port = 8765
    
    handler = GatewayHandler()
    handler.stop(host=host, port=port, force=force)


@app.command("restart")
def gateway_restart(
    host: str = typer.Option("127.0.0.1", "--host", help="Gateway host"),
    port: Optional[int] = typer.Option(None, "--port", help="Gateway port"),
    config: Optional[str] = typer.Option(
        None, "--config", help="Path to gateway.yaml (for direct relaunch)"
    ),
    agents: Optional[str] = typer.Option(
        None, "--agents", help="Path to agent configuration file (for direct relaunch)"
    ),
    drain_timeout: Optional[float] = typer.Option(
        None, "--drain-timeout",
        help="Seconds to wait for in-flight agent turns to finish before "
        "relaunch (default: the persisted start value, else 10)",
    ),
):
    """Gracefully drain in-flight turns, then relaunch the gateway.

    Daemon-aware: if the gateway is installed as an OS service
    (launchd / systemd / scheduled task), the service manager restarts it so
    operators never hand-copy ``launchctl kickstart`` / ``systemctl --user
    restart`` / ``schtasks`` per platform, preserving the installed unit's
    launch arguments. Otherwise it drains the running PID and relaunches
    directly (#3161).

    The direct (non-service) relaunch replays the CLI-only runtime flags the
    original process was started with (e.g. ``--openai-api``,
    ``--reliability``, ``--max-concurrent-runs``) from the persisted start-flags
    artefact written at ``start`` time, so a restart faithfully reproduces the
    running gateway instead of silently reverting to defaults (#3349). Flags
    passed explicitly to ``restart`` still win over the persisted values; an
    omitted ``--drain-timeout`` replays the persisted drain window rather than
    forcing a fixed default.

    Examples:
        praisonai gateway restart
        praisonai gateway restart --config gateway.yaml
        praisonai gateway restart --drain-timeout 30
    """
    import os
    from praisonai_bot.daemon import restart_daemon, get_daemon_status
    from ..features.gateway import GatewayHandler, load_start_flags
    from ..output.console import get_output_controller

    if port is None:
        try:
            port = int(os.environ.get("GATEWAY_PORT", "8765"))
        except ValueError:
            port = 8765

    output = get_output_controller()

    # Daemon-aware path: let the service manager perform the restart when a
    # service is installed, so drain/relaunch semantics match `install`.
    try:
        daemon_status = get_daemon_status()
    except Exception:
        daemon_status = {"installed": False}

    if daemon_status.get("installed"):
        result = restart_daemon()
        if result.get("ok"):
            output.print_success(result.get("message", "Service restarted"))
            return
        output.print_warning(
            f"Daemon restart unavailable ({result.get('error', 'unknown')}); "
            "falling back to direct drain + relaunch."
        )

    # Replay the CLI-only runtime flags the original process was started with so
    # the restart reproduces the exact posture (durable delivery, concurrency
    # ceiling, OpenAI-compat surface, lifecycle) instead of silently reverting
    # to defaults (#3349). Flags passed explicitly to ``restart`` (config /
    # agents / drain_timeout) still win over the persisted values.
    persisted = load_start_flags(host, port)
    start_kwargs = dict(persisted)
    if config is not None:
        start_kwargs["config_file"] = config
    if agents is not None:
        start_kwargs["agent_file"] = agents
    # An omitted --drain-timeout (None) must replay the persisted start value,
    # not clobber it with Typer's old fixed 10s default — otherwise every
    # restart silently shortens a production drain window (#3349). An explicit
    # value still wins over the persisted one.
    if drain_timeout is not None:
        start_kwargs["drain_timeout"] = drain_timeout
    # Effective window for draining the OLD process before relaunch: explicit
    # flag > persisted start value > 10s fallback, so a long configured drain is
    # not cut off by a fixed wait before force-kill (#3161).
    effective_drain = drain_timeout
    if effective_drain is None:
        effective_drain = persisted.get("drain_timeout")
    if effective_drain is None:
        effective_drain = 10.0

    # Direct path: gracefully stop the running gateway (honouring drain), then
    # start a fresh instance in the foreground.
    handler = GatewayHandler()
    handler.stop(host=host, port=port, force=False, drain_timeout=effective_drain)

    if persisted:
        output.print_info(
            "Replaying persisted start flags: "
            + ", ".join(sorted(persisted.keys()))
        )
    output.print_info("Relaunching gateway...")
    handler.start(host=host, port=port, **start_kwargs)


@app.command("status")
def gateway_status(
    host: str = typer.Option("127.0.0.1", "--host", help="Gateway host"),
    port: Optional[int] = typer.Option(None, "--port", help="Gateway port"),
    config: Optional[str] = typer.Option(None, "--config", "-c", help="Gateway config path"),
    daemon_only: bool = typer.Option(False, "--daemon-only", help="Show only daemon status"),
    deep: bool = typer.Option(False, "--deep", help="Extended diagnostics (health + log tail)"),
    probe: bool = typer.Option(False, "--probe", help="Live credential probe per channel"),
):
    """Check gateway status and daemon service status.

    Examples:
        praisonai gateway status
        praisonai gateway status --port 9000
        praisonai gateway status --deep --config bot.yaml
        praisonai gateway status --probe --config bot.yaml
        praisonai gateway status --daemon-only
    """
    import os
    from ..features.gateway import GatewayHandler
    from praisonai_bot.daemon import get_daemon_status
    from ..output.console import get_output_controller
    
    # Check for GATEWAY_PORT environment variable if port not specified
    if port is None:
        try:
            port = int(os.environ.get("GATEWAY_PORT", "8765"))
        except ValueError:
            port = 8765

    # Discover the same onboarded config start/doctor use so --deep/--probe read
    # the file onboarding wrote instead of nothing (#3880).
    if config is None:
        config = _resolve_gateway_config_path(None)

    output = get_output_controller()
    
    # Show daemon status
    try:
        daemon_status = get_daemon_status()
        platform = daemon_status.get("platform", "unknown")
        installed = daemon_status.get("installed", False)
        running = daemon_status.get("running", False)
        
        if installed:
            if running:
                output.print_success(f"Daemon service: Running ({platform})")
            else:
                output.print_warning(f"Daemon service: Installed but not running ({platform})")
        else:
            output.print_info(f"Daemon service: Not installed ({platform})")
            
        if daemon_status.get("pid"):
            output.print_info(f"Process ID: {daemon_status['pid']}")
        if daemon_status.get("error"):
            output.print_warning(f"Daemon error: {daemon_status['error']}")
            
    except Exception as e:
        output.print_error(f"Error checking daemon status: {str(e)}")
    
    # Show gateway server status if not daemon-only
    if not daemon_only:
        try:
            handler = GatewayHandler()
            handler.status(host=host, port=port, deep=deep)
            if deep and config and os.path.exists(config):
                from praisonai_bot.daemon.launchd import get_logs

                output.print_info("Recent log tail:")
                print(get_logs(lines=20))
                channels = _load_channels(config)
                for name, ch in channels.items():
                    platform = (ch or {}).get("platform", name)
                    dlq_path = _resolve_platform_dlq_path(str(platform))
                    output.print_info(
                        f"DLQ ({name}): praisonai bot dlq list --path {dlq_path}"
                    )
            if probe and config and os.path.exists(config):
                import asyncio

                channels = _load_channels(config)
                results = asyncio.run(_probe_channels(channels))
                output.print_info("Live channel probe:")
                _render_probe_results(results, json_output=False)
        except Exception as e:
            output.print_error(f"Error checking gateway server status: {str(e)}")


# Gateway repair machinery lives in the typer-free ``gateway.admin`` module
# so the importable Python API (repair_gateway_config / provision_gateway_config,
# Issue #3985) does not depend on the CLI-only ``typer`` package. They are
# re-imported here so the Typer commands remain thin wrappers over one
# canonical flow (DRY).
from praisonai_bot.gateway.admin import (  # noqa: E402 - re-exported for CLI/tests
    _GatewayConfigVersionHealthCheck,
    _GatewaySecretHealthCheck,
    _check_config_version,
    _check_gateway_secret_strength,
    _config_has_explicit_weak_token,
    _persist_yaml_auth_token,
    _repair_config_version,
    _repair_gateway_secret,
    _run_gateway_health_checks,
)


def _health_result(results, check_id):
    return next((result for result in results if result.check_id == check_id), None)


def _health_payload(results):
    return {
        "checksRun": len(results),
        "repaired": sum(result.repaired for result in results),
        "validated": sum(not result.residual_findings for result in results),
        "results": [result.to_dict() for result in results],
    }


from praisonai_bot.gateway.preflight import (  # noqa: E402 — re-exported for tests/CLI
    apply_probe_ca_bundle as _apply_probe_ca_bundle,
    classify_preflight_action as _classify_preflight_action,
    check_duplicates as _check_duplicates,
    check_gateway_running as _check_gateway_running,
    check_inbound as _check_inbound,
    check_runtime as _check_runtime,
    probe_channels as _probe_channels,
    probe_results_to_dict as _probe_results_to_dict,
    resolve_env_token as _resolve_env_token,
    resolve_platform_dlq_path as _resolve_platform_dlq_path,
    resolve_strict_preflight as _resolve_strict_preflight,
    resolve_verify_turn as _resolve_verify_turn,
    run_shell_readiness_check as _run_shell_readiness_check,
    run_turn_test as _run_gateway_turn_test,
    verify_turn_preflight as _verify_turn_preflight,
)


def _secret_availability(value) -> str:
    """Report a credential's availability WITHOUT printing its value (#3102).

    Returns ``available`` | ``configured-but-unavailable`` | ``missing`` for a
    reference/`${ENV}`/plaintext input so operators can validate secret wiring
    before start.

    An ``exec``-sourced reference is reported as ``configured`` WITHOUT running
    its command: the command has side effects (a one-shot / rate-limited /
    rotating secret-manager call) and the probe resolves the same reference
    moments later, so executing it here would run it twice. env/file/plaintext
    resolution is side-effect-free and fully checked.
    """
    try:
        from praisonaiagents.secrets import resolve_secret, AVAILABLE, MISSING

        if isinstance(value, dict) and value.get("source") == "exec":
            return "configured"

        result = resolve_secret(value, redact=False)
        if result.available:
            return AVAILABLE
        if result.status == MISSING:
            return MISSING
        return result.status
    except Exception:  # pragma: no cover — defensive
        return "missing"


def _is_ssl_error(result) -> bool:
    """True if a failed probe result is an SSL certificate-verify failure.

    On SSL-inspecting networks (corporate proxy / MITM) the probe's HTTP client
    rejects the self-signed CA in the chain even though the runtime bot adapter
    connects fine, so this must be classified separately from bad/expired tokens
    to avoid a misleading "fix credentials" abort (#2845).
    """
    if getattr(result, "ok", False):
        return False
    error = (getattr(result, "error", None) or "").lower()
    return any(
        marker in error
        for marker in (
            "sslcertverificationerror",
            "certificate_verify_failed",
            "certificate verify failed",
            "self-signed certificate",
            "self signed certificate",
            "ssl: certificate",
        )
    )


def _preflight_tools(config: str, strict_tools: bool = True) -> None:
    """Validate that every tool named in the config can be resolved (#3553).

    An unresolved tool reference (typo, uninstalled optional package, or a
    local ``tools.py`` gated behind ``PRAISONAI_ALLOW_LOCAL_TOOLS``) is
    otherwise silently dropped, leaving a quietly under-powered agent. This
    mirrors the credential pre-flight: in strict mode (default) it prints a
    per-name reason + fix hint and aborts; ``strict_tools=False`` (or
    ``strict_tools: false`` in the YAML) warns and continues.

    The CLI ``--strict-tools/--no-strict-tools`` flag wins over the YAML
    ``strict_tools:`` key only when set to non-strict — an explicit YAML
    ``strict_tools: false`` also disables the gate so operators can opt into a
    partial tool set from config alone.
    """
    import yaml

    try:
        with open(config) as fh:
            cfg = yaml.safe_load(fh) or {}
    except Exception:  # pragma: no cover — defensive; start will surface it
        return

    if cfg.get("strict_tools") is False:
        strict_tools = False

    # Load ~/.praisonai/.env before resolving so a local tools.py enabled via
    # PRAISONAI_ALLOW_LOCAL_TOOLS in that file is not falsely rejected — the
    # gate runs before GatewayHandler.start() does the same load, and the
    # runtime resolver would accept it (#3553). Idempotent; existing env wins.
    try:
        from praisonai_bot.cli.features.gateway import _load_praisonai_env_file

        _load_praisonai_env_file()
    except Exception:  # pragma: no cover — never block start on env-load
        pass

    try:
        from praisonai_bot._code_bridge import import_code_module

        resolver_mod = import_code_module("praisonai_code.tool_resolver")
    except Exception:  # pragma: no cover — resolver unavailable in lean install
        return

    unresolved = resolver_mod.validate_yaml_tools(cfg)
    if not unresolved:
        return

    reasons = []
    for name in sorted(unresolved):
        if str(name).startswith("toolset:"):
            reasons.append(f"    - {name} not found (unknown toolset)")
        else:
            reasons.append(f"    - {resolver_mod.describe_unresolved(name)}")

    if strict_tools:
        print("\n\u2717 Tool pre-flight failed:")
        print("\n".join(reasons))
        print(
            "  Fix the names in your config, or start with --no-strict-tools "
            "to run without them."
        )
        raise typer.Exit(78)

    print("\n\u26a0 Tool pre-flight (non-strict) — starting without:")
    print("\n".join(reasons))


def _load_channels(config: str) -> dict:
    """Load the ``channels`` mapping from a gateway.yaml file (or exit)."""
    import os
    import yaml

    if not os.path.exists(config):
        print(f"Error: Config file not found: {config}")
        raise typer.Exit(1)

    with open(config) as f:
        cfg = yaml.safe_load(f) or {}

    return cfg.get("channels", {})


def _compute_secret_availability(channels: dict) -> dict:
    """Per-channel credential availability without revealing values (#3102).

    Reports the ``token`` (and Slack ``app_token`` / WhatsApp ``verify_token``
    when present) as ``available`` | ``configured-but-unavailable`` |
    ``configured`` | ``missing``. Returns ``{channel: {field: status}}``.
    """
    _fields = ("token", "app_token", "verify_token")
    report: dict = {}
    for name, ch_cfg in channels.items():
        ch_cfg = ch_cfg or {}
        fields = {
            f: _secret_availability(ch_cfg[f])
            for f in _fields
            if f in ch_cfg and ch_cfg[f] not in (None, "")
        }
        if fields:
            report[name] = fields
    return report


def _print_secret_availability(report: dict) -> None:
    """Print the availability report as a table (values never shown)."""
    if not report:
        return
    print("Credential availability (values never shown):")
    for name, fields in report.items():
        for f, status in fields.items():
            mark = "✓" if status == "available" else "✗"
            print(f"{name:<12} {f:<13} {mark}  {status}")
    print()


def _render_probe_results(results: dict, json_output: bool = False) -> bool:
    """Print per-channel probe verdicts. Returns True if all channels passed."""
    all_ok = all(getattr(r, "ok", False) for r in results.values())

    if json_output:
        import json

        print(json.dumps(_probe_results_to_dict(results), indent=2))
        return all_ok

    for name, r in results.items():
        mark = "✓" if getattr(r, "ok", False) else "✗"
        identity = getattr(r, "bot_username", None) or ""
        if getattr(r, "ok", False):
            detail = f"@{identity}" if identity else (getattr(r, "platform", "") or "")
        elif _is_ssl_error(r):
            # Distinguish an SSL certificate-verify failure (network/proxy) from
            # a bad/expired token so the operator does not chase a credential
            # problem that does not exist (#2845).
            detail = (
                "SSL certificate verify failed (network/proxy?). "
                "Token may still be valid. Try SSL_CERT_FILE=/path/to/corp-ca.pem "
                "or gateway start --no-preflight"
            )
        else:
            detail = getattr(r, "error", None) or "unknown error"
        print(f"{name:<12} {mark}  {detail}")

    return all_ok


@app.command("doctor")
def gateway_doctor(
    config: str = typer.Option("gateway.yaml", "--config", "-c", help="Path to gateway.yaml"),
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
    channel: Optional[str] = typer.Option(
        None,
        "--channel",
        help="Channel name for --turn (default: first configured channel)",
    ),
    turn: Optional[str] = typer.Option(
        None,
        "--turn",
        help="Run one live inbound agent turn offline (requires LLM API key)",
    ),
    fix: bool = typer.Option(
        False,
        "--fix",
        help=(
            "Repair safe findings: mint a strong gateway auth token when "
            "weak/missing, and migrate an out-of-date gateway.yaml forward "
            "(applies safe config migrations and stamps config_version), "
            "then re-validate"
        ),
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="With --fix, preview repairs without writing anything",
    ),
):
    """Validate every configured channel's credentials (pre-flight check).

    Probes each channel's token and surfaces the bot identity
    (Telegram getMe, Slack auth.test, Discord identify, WhatsApp token check)
    without starting message processing. Exits non-zero if any channel fails.

    Optional ``--turn`` runs an offline inbound agent turn via
    ``BotSessionManager.chat`` (including ``allow_shell`` setup). It does
    **not** exercise Slack Bolt/socket handlers or @mention routing.

    ``--fix`` performs the safe, idempotent repairs its own retry hints promise:
    when ``gateway.auth_token`` is weak/missing it mints a strong token
    (persisted to ``~/.praisonai/.env``) and **re-validates** that the finding
    cleared, and when ``gateway.yaml`` is out of date it atomically rewrites the
    file — applying the canonical config migrations and stamping the current
    ``config_version``. A config written by a newer build is reported and left
    untouched rather than downgraded. Pair with ``--dry-run`` to preview without
    writing.

    Examples:
        praisonai gateway doctor
        praisonai gateway doctor --fix
        praisonai gateway doctor --fix --dry-run
        praisonai gateway doctor --config my-gateway.yaml --json
        praisonai gateway doctor --config gateway.yaml --channel slack --turn "Say OK"
    """
    import asyncio
    import json

    config = _resolve_doctor_config(config)

    health_results = _run_gateway_health_checks(config, fix=fix, dry_run=dry_run)
    auth_health = _health_result(health_results, "core/gateway/auth-token")
    config_health = _health_result(health_results, "core/gateway/config-version")

    gateway_secret_error = None
    auth_check_error = auth_health.error if auth_health else None
    fix_report = None
    if auth_health:
        if auth_health.residual_findings and not auth_check_error:
            gateway_secret_error = auth_health.residual_findings[0].message
        if auth_health.repair:
            if auth_health.repaired:
                fix_report = (
                    "gateway_auth_token: weak → generated a strong token… done\n"
                    "re-validated: gateway_auth_token now strong"
                )
            elif auth_health.repair.changed:
                fix_report = "gateway_auth_token: repair attempted but still weak"
            else:
                fix_report = auth_health.repair.message

    config_migration = None
    config_version_error = None
    config_fix_report = None
    if config_health and config_health.findings:
        finding = config_health.findings[0]
        details = finding.context or {}
        if details.get("unsupported"):
            config_version_error = finding.message
        elif config_health.residual_findings:
            config_migration = (
                list(details.get("reasons", [])),
                details.get("from_version", "unstamped"),
                details.get("to_version", "current"),
            )
        if config_health.repair and config_health.repair.message:
            config_fix_report = config_health.repair.message

    extension_results = [
        result for result in health_results
        if not result.check_id.startswith("core/gateway/")
    ]
    health_failed = any(
        finding.severity == "error"
        for result in health_results
        for finding in result.residual_findings
    )

    if not json_output:
        if fix_report:
            print(fix_report)
        if config_version_error:
            print(f"config: {config_version_error}")
        if config_fix_report:
            print(config_fix_report)
        summary = _health_payload(health_results)
        print(
            "health checks: "
            f"{summary['checksRun']} run, {summary['repaired']} repaired, "
            f"{summary['validated']} validated"
        )
        for result in extension_results:
            for finding in result.residual_findings:
                hint = f"; fix: {finding.fix_description}" if finding.fix_description else ""
                print(
                    f"{result.check_id}: {finding.severity}: "
                    f"{finding.message}{hint}"
                )

    channels = _load_channels(config)

    if not channels:
        payload: dict = {"probes": {}}
        payload["health"] = _health_payload(health_results)
        if gateway_secret_error:
            payload["gateway_auth_token"] = "weak"
        if auth_check_error:
            payload["gateway_auth_token_check_error"] = auth_check_error
        if config_migration:
            payload["config_version"] = "out-of-date"
        if config_version_error:
            payload["config_version"] = "unsupported"
            payload["config_version_error"] = config_version_error
        if fix_report:
            payload["fix"] = fix_report
        if config_fix_report:
            payload["config_fix"] = config_fix_report
        if json_output:
            print(json.dumps(payload, indent=2))
        else:
            print("No channels configured.")
            if gateway_secret_error:
                print(gateway_secret_error)
        if health_failed:
            raise typer.Exit(1)
        raise typer.Exit(0)

    availability = _compute_secret_availability(channels)
    results = asyncio.run(_probe_channels(channels))
    all_ok = all(getattr(r, "ok", False) for r in results.values())
    turn_gate_ok = all_ok
    if channel and channel in results:
        turn_gate_ok = getattr(results[channel], "ok", False)

    payload: dict = {
        "probes": _probe_results_to_dict(results),
        "health": _health_payload(health_results),
    }
    if availability:
        payload["secrets"] = availability
    if gateway_secret_error:
        payload["gateway_auth_token"] = "weak"
    if auth_check_error:
        payload["gateway_auth_token_check_error"] = auth_check_error
    if config_migration:
        payload["config_version"] = "out-of-date"
    if config_version_error:
        payload["config_version"] = "unsupported"
        payload["config_version_error"] = config_version_error
    if fix_report:
        payload["fix"] = fix_report
    if config_fix_report:
        payload["config_fix"] = config_fix_report

    if not json_output:
        _print_secret_availability(availability)
        _render_probe_results(results, json_output=False)
        if gateway_secret_error:
            print(gateway_secret_error)
        if config_migration:
            print(
                "config: out of date (config_version "
                f"{config_migration[1]} -> {config_migration[2]}); "
                "run 'gateway doctor --fix'"
            )

    if health_failed:
        if json_output:
            print(json.dumps(payload, indent=2))
        raise typer.Exit(1)

    probe_blocks_turn = not all_ok and not (turn and channel and turn_gate_ok)
    if probe_blocks_turn and not turn:
        if json_output:
            print(json.dumps(payload, indent=2))
        raise typer.Exit(1)

    if turn:
        target = channel or (next(iter(channels.keys())) if channels else None)
        if not target:
            err = "--turn requires at least one configured channel"
            payload["turn"] = {"channel": None, "ok": False, "response": err}
            if json_output:
                print(json.dumps(payload, indent=2))
            else:
                print(f"Error: {err}")
            raise typer.Exit(1)
        if not turn_gate_ok:
            err = f"channel '{target}' probe failed — cannot run --turn"
            payload["turn"] = {"channel": target, "ok": False, "response": err}
            if json_output:
                print(json.dumps(payload, indent=2))
            else:
                print(f"Error: {err}")
            raise typer.Exit(1)
        ok, message = asyncio.run(_run_gateway_turn_test(config, target, turn))
        payload["turn"] = {"channel": target, "ok": ok, "response": message}
        if json_output:
            print(json.dumps(payload, indent=2))
        else:
            print(f"\nTurn test ({target}): {'OK' if ok else 'FAIL'}")
            print(message if ok else f"Error: {message}")
        if not ok or not all_ok:
            raise typer.Exit(1)
        return

    if json_output:
        print(json.dumps(payload, indent=2))
    if not all_ok:
        raise typer.Exit(1)


@app.command("test")
def gateway_test(
    config: str = typer.Option("gateway.yaml", "--config", "-c", help="Path to gateway.yaml"),
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
    channel: Optional[str] = typer.Option(
        None,
        "--channel",
        help="Channel name for --turn (default: first configured channel)",
    ),
    turn: Optional[str] = typer.Option(
        None,
        "--turn",
        help="Run one live inbound agent turn offline (requires LLM API key)",
    ),
    check_running: bool = typer.Option(
        False,
        "--check-running",
        help="Verify the gateway REST /info endpoint is reachable",
    ),
    check_runtime: bool = typer.Option(
        False,
        "--check-runtime",
        help="Probe /info, /health, /ready, and /live (superset of --check-running)",
    ),
    check_inbound: bool = typer.Option(
        False,
        "--check-inbound",
        help="Verify recent inbound delivery via gateway logs",
    ),
    check_duplicates: bool = typer.Option(
        False,
        "--check-duplicates",
        help="Scan for competing gateway services and shared tokens",
    ),
    since: str = typer.Option(
        "10m",
        "--since",
        help="Time window for --check-inbound (e.g. 5m, 2h)",
    ),
):
    """One-shot gateway readiness check (probes + shell wiring + optional turn).

    Recommended onboarding path before ``gateway start``. Combines credential
    probes, offline shell wiring validation, and optional offline agent turn.

    ``--turn`` uses ``BotSessionManager.chat`` only — it does not prove live
    Slack @mention delivery. After starting, confirm ``@mention received`` in
    gateway logs or use ``--check-inbound``.

    Examples:
        praisonai gateway test --config bot.yaml
        praisonai gateway test --config bot.yaml --channel slack --turn "Say OK"
        praisonai gateway test --config bot.yaml --check-runtime --check-duplicates
        praisonai gateway test --config bot.yaml --check-inbound --since 5m
    """
    import asyncio
    import json

    config = _resolve_doctor_config(config)

    gateway_secret_error = _check_gateway_secret_strength(config)
    channels = _load_channels(config)
    payload: dict = {}

    if gateway_secret_error:
        payload["gateway_auth_token"] = "weak"

    if not channels:
        payload.setdefault("probes", {})
        if json_output:
            print(json.dumps(payload, indent=2))
        else:
            print("No channels configured.")
            if gateway_secret_error:
                print(gateway_secret_error)
        raise typer.Exit(1 if gateway_secret_error else 0)

    availability = _compute_secret_availability(channels)
    results = asyncio.run(_probe_channels(channels))
    all_ok = all(getattr(r, "ok", False) for r in results.values())
    turn_gate_ok = all_ok
    if channel and channel in results:
        turn_gate_ok = getattr(results[channel], "ok", False)

    payload["probes"] = _probe_results_to_dict(results)
    if availability:
        payload["secrets"] = availability

    shell_result = _run_shell_readiness_check(config)
    payload["shell"] = {
        "ok": shell_result.ok,
        "message": shell_result.message,
        "issues": shell_result.issues,
    }

    if not json_output:
        _print_secret_availability(availability)
        _render_probe_results(results, json_output=False)
        shell_mark = "✓" if shell_result.ok else "✗"
        print(f"shell wiring  {shell_mark}  {shell_result.message}")
        if shell_result.issues:
            for issue in shell_result.issues:
                print(f"  - {issue}")
        if gateway_secret_error:
            print(gateway_secret_error)

    failed = bool(gateway_secret_error) or not all_ok or not shell_result.ok

    runtime_requested = check_runtime or check_running
    if runtime_requested:
        if check_runtime:
            runtime_result = _check_runtime(config)
            payload["runtime"] = runtime_result.to_dict()
            runtime_ok = runtime_result.ok
            if not json_output:
                for name, key in (
                    ("info", "info"),
                    ("health", "health"),
                    ("ready", "ready"),
                    ("live", "live"),
                ):
                    probe = getattr(runtime_result, key)
                    mark = "✓" if probe.ok else "✗"
                    print(f"gateway {name:<6} {mark}  HTTP {probe.status_code or '—'}")
        else:
            running_ok, running_msg = _check_gateway_running(config)
            payload["running"] = {"ok": running_ok, "message": running_msg}
            runtime_ok = running_ok
            if not json_output:
                mark = "✓" if running_ok else "✗"
                print(f"gateway up    {mark}  {running_msg}")
        failed = failed or not runtime_ok

    if check_duplicates:
        dup_result = _check_duplicates(config)
        payload["duplicates"] = dup_result.to_dict()
        if not json_output:
            mark = "✓" if dup_result.ok else "✗"
            print(f"duplicates  {mark}  {len(dup_result.warnings)} warning(s)")
            for warning in dup_result.warnings:
                print(f"  - {warning}")
        failed = failed or not dup_result.ok

    if check_inbound:
        inbound_result = _check_inbound(
            config,
            since=since,
            probe_results=results,
        )
        payload["inbound"] = inbound_result.to_dict()
        if not json_output:
            mark = "✓" if inbound_result.ok else "✗"
            print(
                f"inbound     {mark}  "
                f"{inbound_result.mentions_in_window} mention(s) in window "
                f"(proves {inbound_result.proves})"
            )
            if inbound_result.last_mention_at:
                print(f"  last: {inbound_result.last_mention_at}")
            if inbound_result.hint:
                print(f"  hint: {inbound_result.hint}")
        failed = failed or not inbound_result.ok

    if turn:
        target = channel or (next(iter(channels.keys())) if channels else None)
        if not target:
            err = "--turn requires at least one configured channel"
            payload["turn"] = {"channel": None, "ok": False, "response": err}
            if json_output:
                print(json.dumps(payload, indent=2))
            else:
                print(f"Error: {err}")
            raise typer.Exit(1)
        if not turn_gate_ok:
            err = f"channel '{target}' probe failed — cannot run --turn"
            payload["turn"] = {"channel": target, "ok": False, "response": err}
            if json_output:
                print(json.dumps(payload, indent=2))
            else:
                print(f"Error: {err}")
            raise typer.Exit(1)
        ok, message = asyncio.run(_run_gateway_turn_test(config, target, turn))
        payload["turn"] = {"channel": target, "ok": ok, "response": message}
        if not json_output:
            print(f"\nTurn test ({target}): {'OK' if ok else 'FAIL'}")
            print(message if ok else f"Error: {message}")
        failed = failed or not ok

    if json_output:
        print(json.dumps(payload, indent=2))

    if failed:
        raise typer.Exit(1)


@app.command("channels")
def gateway_channels(
    config: str = typer.Option("gateway.yaml", "--config", "-c", help="Path to gateway.yaml"),
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
    probe: bool = typer.Option(False, "--probe", help="Probe each channel's credentials"),
    available: bool = typer.Option(
        False, "--available",
        help="List all registered platforms (built-in + entry-point + custom)",
    ),
):
    """List channels configured in a gateway.yaml file.

    Examples:
        praisonai gateway channels
        praisonai gateway channels --config my-gateway.yaml --json
        praisonai gateway channels --probe
        praisonai gateway channels --available
    """
    import os
    import yaml

    if available:
        try:
            from praisonai_bot.bots._registry import list_platforms
            platforms = sorted(list_platforms())
        except Exception as exc:
            print(f"Error: could not load platform registry: {exc}")
            raise typer.Exit(1) from exc

        if json_output:
            import json
            print(json.dumps(platforms, indent=2))
            raise typer.Exit(0)

        try:
            from rich.table import Table
            from rich.console import Console

            console = Console()
            table = Table(title="Available Platforms")
            table.add_column("Platform", style="green")
            for platform in platforms:
                table.add_row(platform)
            console.print(table)
        except ImportError:
            print("Available platforms:")
            for platform in platforms:
                print(f"  - {platform}")
        raise typer.Exit(0)

    config = _resolve_doctor_config(config)

    if not os.path.exists(config):
        print(f"Error: Config file not found: {config}")
        raise typer.Exit(1)

    with open(config) as f:
        cfg = yaml.safe_load(f) or {}

    channels = cfg.get("channels", {})

    if not channels:
        print("No channels configured.")
        raise typer.Exit(0)

    if probe:
        import asyncio

        results = asyncio.run(_probe_channels(channels))
        all_ok = _render_probe_results(results, json_output=json_output)
        if not all_ok:
            raise typer.Exit(1)
        raise typer.Exit(0)

    if json_output:
        import json
        print(json.dumps(channels, indent=2))
        raise typer.Exit(0)

    try:
        from rich.table import Table
        from rich.console import Console

        console = Console()
        table = Table(title="Configured Channels")
        table.add_column("Name", style="cyan")
        table.add_column("Platform", style="green")
        table.add_column("Token", style="yellow")
        table.add_column("Config Keys", style="dim")

        for name, ch_cfg in channels.items():
            platform = ch_cfg.get("platform", "unknown")
            token_val = ch_cfg.get("token", "")
            has_token = "✅ set" if token_val else "❌ missing"
            keys = ", ".join(
                k for k in ch_cfg.keys() if k not in ("platform", "token")
            )
            table.add_row(name, platform, has_token, keys or "—")

        console.print(table)
    except ImportError:
        print(f"{'Name':<20} {'Platform':<12} {'Token':<12}")
        print("-" * 44)
        for name, ch_cfg in channels.items():
            platform = ch_cfg.get("platform", "unknown")
            has_token = "set" if ch_cfg.get("token") else "missing"
            print(f"{name:<20} {platform:<12} {has_token:<12}")


def _resolve_gateway_rest_url(
    url: Optional[str],
    host: Optional[str] = None,
    port: Optional[int] = None,
) -> str:
    """Resolve the gateway REST base URL for channel control commands.

    When ``--url`` is not passed, resolve the running gateway from the PID
    lock/config (host+port) rather than forcing the operator to hand-type a
    WebSocket URL (#3161). The lock file is keyed by host+port, so an explicit
    ``--host``/``--port`` (or ``GATEWAY_PORT``) is honoured to locate a gateway
    bound to a non-default endpoint; otherwise it falls back to
    ``127.0.0.1:8765``. An explicit ``--url`` (ws/wss/http/https) always wins.
    """
    import os
    from urllib.parse import urlparse, urlunparse

    if url:
        parsed = urlparse(url)
        scheme = "https" if parsed.scheme in ("wss", "https") else "http"
    else:
        resolved_host = host or "127.0.0.1"
        if port is None:
            try:
                resolved_port = int(os.environ.get("GATEWAY_PORT", "8765"))
            except ValueError:
                resolved_port = 8765
        else:
            resolved_port = port
        try:
            from praisonai_bot.gateway.port_utils import GatewayPIDLock

            # Key the lock lookup by the requested host+port so a gateway on a
            # non-default endpoint is found instead of silently probing 8765.
            info = GatewayPIDLock(
                host=resolved_host, port=resolved_port
            ).get_lock_info()
            if info and info.get("is_running"):
                resolved_host, resolved_port = info["host"], info["port"]
        except Exception:  # pragma: no cover — advisory only
            pass
        parsed = urlparse(f"http://{resolved_host}:{resolved_port}")
        scheme = "http"

    rest_url = urlunparse(
        (scheme, parsed.netloc, parsed.path, parsed.params, parsed.query, parsed.fragment)
    )
    if not rest_url.endswith("/"):
        rest_url += "/"
    return rest_url


def _channel_control(
    name: str,
    action: str,
    url: Optional[str],
    host: Optional[str] = None,
    port: Optional[int] = None,
) -> None:
    """POST a pause/resume/reconnect action to the running gateway."""
    import requests
    import sys

    rest_url = _resolve_gateway_rest_url(url, host=host, port=port)
    try:
        response = requests.post(f"{rest_url}api/channels/{name}/{action}", timeout=10)
        response.raise_for_status()

        result = response.json()
        if result.get("success"):
            print(f"✅ Channel '{name}' {action}{'ed' if action != 'pause' else 'd'} successfully")
        else:
            message = result.get("message", result.get("error", "Unknown error"))
            print(f"❌ Failed to {action} channel '{name}': {message}")
            sys.exit(1)
    except SystemExit:
        raise
    except Exception as e:
        print(f"❌ Error running {action} on channel '{name}': {str(e)}")
        sys.exit(1)


@app.command("pause")
def gateway_pause_channel(
    name: str = typer.Argument(help="Channel name to pause"),
    url: Optional[str] = typer.Option(
        None, "--url",
        help="Gateway WebSocket/HTTP URL (default: resolved from the PID lock)",
    ),
    host: Optional[str] = typer.Option(
        None, "--host", help="Gateway host to locate (for non-default binds)",
    ),
    port: Optional[int] = typer.Option(
        None, "--port", help="Gateway port to locate (for non-default binds)",
    ),
):
    """Pause a gateway channel.

    Resolves the running gateway from the PID lock when --url is omitted;
    pass --host/--port to control a gateway bound to a non-default endpoint.

    Examples:
        praisonai gateway pause telegram
        praisonai gateway pause discord --url ws://localhost:8000
        praisonai gateway pause telegram --port 9000
    """
    _channel_control(name, "pause", url, host=host, port=port)


@app.command("resume")
def gateway_resume_channel(
    name: str = typer.Argument(help="Channel name to resume"),
    url: Optional[str] = typer.Option(
        None, "--url",
        help="Gateway WebSocket/HTTP URL (default: resolved from the PID lock)",
    ),
    host: Optional[str] = typer.Option(
        None, "--host", help="Gateway host to locate (for non-default binds)",
    ),
    port: Optional[int] = typer.Option(
        None, "--port", help="Gateway port to locate (for non-default binds)",
    ),
):
    """Resume a paused gateway channel.

    Resolves the running gateway from the PID lock when --url is omitted;
    pass --host/--port to control a gateway bound to a non-default endpoint.

    Examples:
        praisonai gateway resume telegram
        praisonai gateway resume discord --url ws://localhost:8000
        praisonai gateway resume telegram --port 9000
    """
    _channel_control(name, "resume", url, host=host, port=port)


@app.command("reconnect")
def gateway_reconnect_channel(
    name: str = typer.Argument(help="Channel name to reconnect"),
    url: Optional[str] = typer.Option(
        None, "--url",
        help="Gateway WebSocket/HTTP URL (default: resolved from the PID lock)",
    ),
    host: Optional[str] = typer.Option(
        None, "--host", help="Gateway host to locate (for non-default binds)",
    ),
    port: Optional[int] = typer.Option(
        None, "--port", help="Gateway port to locate (for non-default binds)",
    ),
):
    """Reconnect a gateway channel.

    Resolves the running gateway from the PID lock when --url is omitted;
    pass --host/--port to control a gateway bound to a non-default endpoint.

    Examples:
        praisonai gateway reconnect telegram
        praisonai gateway reconnect discord --url ws://localhost:8000
        praisonai gateway reconnect telegram --port 9000
    """
    _channel_control(name, "reconnect", url, host=host, port=port)


@app.command("install")
def gateway_install(
    config: str = typer.Option(
        "bot.yaml", "--config",
        help="Path to bot.yaml (defaults to ./bot.yaml → ~/.praisonai/bot.yaml)",
    ),
    start: bool = typer.Option(True, "--start/--no-start", help="Start after install"),
):
    """Install the gateway as an OS daemon (LaunchAgent / systemd).
    
    Examples:
        praisonai gateway install
        praisonai gateway install --config my-bot.yaml --no-start
    """
    from praisonai_bot.daemon import install_daemon
    from praisonai_bot._code_bridge import import_code_module
    from ..output.console import get_output_controller

    resolve_bot_config_path = import_code_module("praisonai_code.cli._paths").resolve_bot_config_path
    
    output = get_output_controller()
    config = resolve_bot_config_path(config)
    
    try:
        result = install_daemon(config_path=config)
        if result.get("ok"):
            output.print_success(result.get("message", "Service installed successfully"))
            if start:
                output.print_info("Starting the service...")
                from praisonai_bot.daemon import get_daemon_status
                status = get_daemon_status()
                if status.get("running"):
                    output.print_success("Service is now running")
                else:
                    output.print_warning("Service installed but not running. Check system logs.")
        else:
            error = result.get("error", "Installation failed")
            output.print_error(f"Installation failed: {error}")
            raise typer.Exit(1)
    except Exception as e:
        output.print_error(f"Installation error: {str(e)}")
        raise typer.Exit(1)


@app.command("uninstall")
def gateway_uninstall():
    """Uninstall the gateway daemon service.
    
    Examples:
        praisonai gateway uninstall
    """
    from praisonai_bot.daemon import uninstall_daemon
    from ..output.console import get_output_controller
    
    output = get_output_controller()
    
    try:
        result = uninstall_daemon()
        if result.get("ok"):
            output.print_success(result.get("message", "Service uninstalled successfully"))
        else:
            error = result.get("error", "Uninstallation failed")
            output.print_error(f"Uninstallation failed: {error}")
            raise typer.Exit(1)
    except Exception as e:
        output.print_error(f"Uninstallation error: {str(e)}")
        raise typer.Exit(1)


@app.command("mint-link")
def gateway_mint_link(
    ttl: int = typer.Option(600, "--ttl", help="Time-to-live in seconds (default: 600 = 10 minutes)"),
    host: str = typer.Option("127.0.0.1", "--host", help="Gateway host"),
    port: int = typer.Option(8765, "--port", help="Gateway port"),
):
    """Generate a fresh magic link for gateway authentication.
    
    Magic links provide one-click authentication without needing to
    copy/paste tokens. Links expire after the specified TTL and can
    only be used once.
    
    Examples:
        praisonai gateway mint-link
        praisonai gateway mint-link --ttl 300  # 5 minutes
        praisonai gateway mint-link --port 9000
    """
    from ..commands.mint_link import mint_fresh_link
    from ..output.console import get_output_controller
    import os
    
    output = get_output_controller()
    
    try:
        # Set environment for host/port override
        os.environ["GATEWAY_HOST"] = host
        os.environ["GATEWAY_PORT"] = str(port)
        
        magic_url = mint_fresh_link(ttl=ttl)
        
        output.print_success("Magic link generated:")
        print(f"\n{magic_url}\n")
        output.print_info(f"Expires in {ttl} seconds ({ttl//60} minutes)")
        output.print_info("Link saved to ~/.praisonai/last-link.txt")
        
    except Exception as e:
        output.print_error(f"Failed to generate magic link: {str(e)}")
        raise typer.Exit(1)


@app.command("logs")
def gateway_logs(
    lines: int = typer.Option(50, "-n", help="Number of log lines to show"),
):
    """Show daemon service logs.
    
    Examples:
        praisonai gateway logs
        praisonai gateway logs -n 100
    """
    from praisonai_bot.daemon import _detect_platform
    from ..output.console import get_output_controller
    import subprocess
    import sys
    
    output = get_output_controller()
    plat = _detect_platform()
    
    try:
        if plat == "systemd":
            from praisonai_bot.daemon.systemd import get_logs
            logs = get_logs(lines=lines)
            if logs:
                print(logs)
            else:
                output.print_warning("No logs found or service not installed")
        elif plat == "launchd":
            from praisonai_bot.daemon.launchd import get_logs
            logs = get_logs(lines=lines)
            if logs:
                print(logs)
            else:
                output.print_warning("No logs found or service not installed")
        elif plat == "windows":
            from praisonai_bot.daemon.windows import get_logs
            logs = get_logs(lines=lines)
            if logs:
                print(logs)
            else:
                output.print_warning("No logs found")
        else:
            output.print_error(f"Unsupported platform: {plat}")
            raise typer.Exit(1)
    except Exception as e:
        output.print_error(f"Error reading logs: {str(e)}")
        raise typer.Exit(1)


@app.command("send")
def gateway_send(
    config: str = typer.Option("gateway.yaml", "--config", "-c", help="Path to gateway.yaml"),
    channel: str = typer.Option(..., "--channel", help="Channel name from config (e.g. 'telegram')"),
    channel_id: str = typer.Option(..., "--channel-id", help="Target chat/channel ID"),
    message: str = typer.Option(..., "--message", "-m", help="Message text to send"),
    thread_id: Optional[str] = typer.Option(None, "--thread-id", help="Optional thread ID"),
):
    """Send a one-shot test message to a channel bot.

    Instantiates the bot from gateway.yaml config, sends the message, then exits.
    Useful for testing scheduled delivery targets.

    Examples:
        praisonai gateway send --config gateway.yaml --channel telegram --channel-id 12345 -m "Hello"
    """
    import os
    import asyncio
    import yaml

    config = _resolve_doctor_config(config)

    if not os.path.exists(config):
        print(f"Error: Config file not found: {config}")
        raise typer.Exit(1)

    with open(config) as f:
        cfg = yaml.safe_load(f) or {}

    channels_cfg = cfg.get("channels", {})
    ch_cfg = channels_cfg.get(channel)

    if not ch_cfg:
        available = ", ".join(channels_cfg.keys()) if channels_cfg else "(none)"
        print(f"Error: Channel '{channel}' not found in config. Available: {available}")
        raise typer.Exit(1)

    platform = ch_cfg.get("platform", channel)
    token = ch_cfg.get("token", "")

    # Resolve env vars in token
    if token and token.startswith("${") and token.endswith("}"):
        env_var = token[2:-1]
        token = os.environ.get(env_var, "")
        if not token:
            print(f"Error: Environment variable {env_var} not set")
            raise typer.Exit(1)

    async def _send():
        try:
            from praisonai_bot.gateway.server import WebSocketGateway
            bot = WebSocketGateway._create_bot(channel, ch_cfg)
        except Exception as e:
            print(f"Error creating bot: {e}")
            raise typer.Exit(1)

        try:
            await bot.start()
            await asyncio.sleep(1)  # Let bot initialise
            result = await bot.send_message(
                channel_id, message, thread_id=thread_id,
            )
            print(f"✅ Message sent to {channel}:{channel_id}")
            if hasattr(result, "message_id"):
                print(f"   Message ID: {result.message_id}")
        except Exception as e:
            print(f"❌ Send failed: {e}")
            raise typer.Exit(1)
        finally:
            try:
                await bot.stop()
            except Exception:
                pass

    try:
        asyncio.run(_send())
    except typer.Exit:
        raise
    except Exception as e:
        print(f"Error: {e}")
        raise typer.Exit(1)


hooks_app = typer.Typer(
    help="Manage inbound trigger hooks (POST /hooks/<path>) in gateway.yaml",
    no_args_is_help=True,
)
app.add_typer(hooks_app, name="hooks")


sessions_app = typer.Typer(
    help="Inspect stored gateway conversation sessions",
    no_args_is_help=True,
)
app.add_typer(sessions_app, name="sessions")


diagnostics_app = typer.Typer(
    help="Produce a portable, pre-sanitised support bundle for the gateway",
    no_args_is_help=True,
)
app.add_typer(diagnostics_app, name="diagnostics")


@diagnostics_app.command("export")
def gateway_diagnostics_export(
    config: str = typer.Option(
        "gateway.yaml", "--config", "-c", help="Path to gateway.yaml"
    ),
    output_dir: Optional[str] = typer.Option(
        None, "--output-dir",
        help="Directory to write the bundle (default: ~/.praisonai/diagnostics)",
    ),
    log_lines: int = typer.Option(
        200, "--log-lines", help="Number of recent (redacted) log lines to include"
    ),
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
):
    """Write a single, pre-sanitised diagnostics archive for a bug report.

    Consolidates a human-readable summary, machine-readable diagnostics, the
    sanitised config *shape* (keys/modes only — no secrets), redacted recent
    log summaries, best-effort health/status, and the latest forensics snapshot
    into one ``.zip``. It runs even when the gateway is unhealthy (falling back
    to local logs) and never includes chat text, prompts, tool outputs,
    credentials, or raw tokens — safe to attach to an issue.

    Examples:
        praisonai gateway diagnostics export
        praisonai gateway diagnostics export --config gateway.yaml
        praisonai gateway diagnostics export --json
    """
    import json
    import os

    from praisonai_bot.gateway.diagnostics import build_diagnostics_bundle

    config = _resolve_doctor_config(config)
    config_path = config if config and os.path.exists(config) else None

    result = build_diagnostics_bundle(
        config_path, output_dir=output_dir, log_lines=log_lines
    )

    if json_output:
        print(json.dumps({"path": result["path"], "manifest": result["manifest"]}, indent=2))
    else:
        print(f"Wrote diagnostics bundle: {result['path']}")
        print(
            "Pre-sanitised (config shape only, secrets redacted, no chat/prompt "
            "data) — safe to attach to a bug report."
        )


@sessions_app.command("list")
def gateway_sessions_list(
    platform: Optional[str] = typer.Option(None, "--platform", help="Filter by platform (e.g. slack)"),
    active: Optional[int] = typer.Option(None, "--active", help="Only sessions updated within N seconds"),
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
):
    """List stored bot session files under ~/.praisonai/sessions/."""
    import json

    from praisonai_bot.gateway.preflight import list_gateway_sessions

    rows = list_gateway_sessions(platform=platform, active_seconds=active)
    if json_output:
        print(json.dumps(rows, indent=2))
    else:
        if not rows:
            print("No sessions found.")
        for row in rows:
            print(
                f"{row['session_id']:<40} "
                f"msgs={row['message_count']:<4} "
                f"user={row.get('user_id') or '—'}"
            )
        print(
            "\nSessions reflect stored history; use "
            "`praisonai gateway test --check-inbound` for live delivery."
        )


@sessions_app.command("show")
def gateway_sessions_show(
    session_ref: str = typer.Argument(..., help="Session id, user id, or partial filename match"),
    tail: int = typer.Option(20, "--tail", help="Number of recent messages to show"),
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
):
    """Show a stored session's recent messages."""
    import json

    from praisonai_bot.gateway.preflight import show_gateway_session

    try:
        data = show_gateway_session(session_ref, tail=tail)
    except FileNotFoundError as exc:
        print(f"Error: {exc}")
        raise typer.Exit(1) from exc

    if json_output:
        print(json.dumps(data, indent=2))
    else:
        print(f"Session: {data.get('session_id')}  user={data.get('user_id')}")
        print(f"Agent: {data.get('agent_name')}  messages={data.get('message_count')}")
        for msg in data.get("messages") or []:
            role = msg.get("role", "?")
            content = (msg.get("content") or "")[:200]
            print(f"  [{role}] {content}")
        print(f"\n{data.get('footer')}")


@sessions_app.command("export")
def gateway_sessions_export(
    session_id: Optional[str] = typer.Option(
        None, "--session-id", "-s",
        help="Export just this session (lineage-aware); default: all sessions",
    ),
    out: Optional[str] = typer.Option(
        None, "--out", "-o", help="Write the payload to this file (default: stdout)"
    ),
    no_lineage: bool = typer.Option(
        False, "--no-lineage",
        help="Do not include compacted/rotated ancestors of a single session",
    ),
):
    """Export gateway conversation sessions to a portable, versioned JSON payload.

    Backup / migrate the gateway's own conversation state — the same store the
    bot persists to — so it can be restored on another host or environment.

    Examples:
        praisonai gateway sessions export --out backup.json
        praisonai gateway sessions export -s bot_slack_U123 -o one.json
    """
    import json

    from praisonai_bot.gateway.preflight import export_gateway_sessions

    payload = export_gateway_sessions(
        session_id=session_id, include_lineage=not no_lineage
    )
    text = json.dumps(payload, indent=2)
    if out:
        # Write to a temp file in the destination dir, then atomically replace
        # so a failed/partial write never truncates or corrupts an existing
        # backup at ``out``.
        import os
        import tempfile

        dest_dir = os.path.dirname(os.path.abspath(out)) or "."
        tmp_fd, tmp_path = tempfile.mkstemp(dir=dest_dir, suffix=".tmp")
        try:
            with os.fdopen(tmp_fd, "w", encoding="utf-8") as handle:
                handle.write(text)
            os.replace(tmp_path, out)
        except OSError as exc:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            print(f"Error: could not write export to {out}: {exc}")
            raise typer.Exit(1) from exc
        print(f"Exported {len(payload.get('sessions') or [])} session(s) -> {out}")
    else:
        print(text)


@sessions_app.command("import")
def gateway_sessions_import(
    in_path: str = typer.Option(
        ..., "--in", "-i", help="Read the exported payload from this file"
    ),
    overwrite: bool = typer.Option(
        False, "--overwrite", help="Overwrite sessions that already exist"
    ),
    keep_live_fields: bool = typer.Option(
        False, "--keep-live-fields",
        help="Do NOT reset live routing/activity fields (advanced)",
    ),
    max_sessions: int = typer.Option(
        10_000, "--max-sessions", help="Cap on how many sessions to ingest"
    ),
    json_output: bool = typer.Option(False, "--json", help="Output JSON report"),
):
    """Import (restore/migrate) gateway sessions from an exported payload.

    Hardened: caps ingest, skips duplicates, and by default resets live
    routing/activity fields so restored state is inert until re-bound.

    Examples:
        praisonai gateway sessions import --in backup.json
        praisonai gateway sessions import -i backup.json --overwrite
    """
    import json

    from praisonai_bot.gateway.preflight import import_gateway_sessions

    try:
        with open(in_path, encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"Error: could not read payload: {exc}")
        raise typer.Exit(1) from exc

    report = import_gateway_sessions(
        payload,
        max_sessions=max_sessions,
        reset_live_fields=not keep_live_fields,
        overwrite=overwrite,
    )

    if json_output:
        print(json.dumps(report, indent=2))
    else:
        print(
            f"Imported {report['imported']} session(s); "
            f"skipped {report['skipped_count']}."
        )
        for entry in report.get("skipped") or []:
            print(f"  skipped {entry.get('session_id') or '?'}: {entry.get('reason')}")


def _run_hooks_action(**kwargs) -> None:
    """Reuse GatewayHandler.hooks() by adapting kwargs to its Namespace API."""
    from types import SimpleNamespace
    from ..features.gateway import GatewayHandler

    code = GatewayHandler().hooks(SimpleNamespace(**kwargs))
    if code:
        raise typer.Exit(code)


@hooks_app.command("add")
def gateway_hooks_add(
    path: str = typer.Argument(..., help="Hook path, e.g. 'gmail' -> POST /hooks/gmail"),
    agent: Optional[str] = typer.Option(None, "--agent", help="Agent id to run (default: first agent)"),
    action_type: str = typer.Option(
        "agent", "--action",
        help="agent runs a turn, wake nudges a session (agent | wake)",
    ),
    auth: Optional[str] = typer.Option(None, "--auth", help="Bearer token / shared secret for this hook"),
    session_key: Optional[str] = typer.Option(None, "--session-key", help="Session key template"),
    idempotency_key: Optional[str] = typer.Option(None, "--idempotency-key", help="Idempotency key template"),
    deliver_to: Optional[str] = typer.Option(None, "--deliver-to", help="channel:target for the reply"),
    message: Optional[str] = typer.Option(None, "--message", help="Message template from the payload"),
    config: str = typer.Option("gateway.yaml", "--config", help="Path to gateway.yaml"),
):
    """Add an inbound trigger hook to gateway.yaml.

    Examples:
        praisonai gateway hooks add gmail --agent inbox --deliver-to telegram:12345
    """
    _run_hooks_action(
        hooks_command="add", path=path, agent=agent, action_type=action_type,
        auth=auth, session_key=session_key, idempotency_key=idempotency_key,
        deliver_to=deliver_to, message=message, config_file=config,
    )


@hooks_app.command("list")
def gateway_hooks_list(
    config: str = typer.Option("gateway.yaml", "--config", help="Path to gateway.yaml"),
):
    """List configured inbound trigger hooks.

    Examples:
        praisonai gateway hooks list
    """
    _run_hooks_action(hooks_command="list", config_file=config)


@hooks_app.command("remove")
def gateway_hooks_remove(
    path: str = typer.Argument(..., help="Hook path to remove"),
    config: str = typer.Option("gateway.yaml", "--config", help="Path to gateway.yaml"),
):
    """Remove an inbound trigger hook from gateway.yaml.

    Examples:
        praisonai gateway hooks remove gmail
    """
    _run_hooks_action(hooks_command="remove", path=path, config_file=config)


@app.callback(invoke_without_command=True)
def gateway_callback(ctx: typer.Context):
    """Show gateway help if no subcommand provided."""
    if ctx.invoked_subcommand is None:
        help_text = """
[bold cyan]PraisonAI Gateway - Multi-Bot WebSocket Server[/bold cyan]

Manage the gateway server: praisonai gateway <command>

[bold]Commands:[/bold]
  [green]start[/green]       Start the gateway server
  [green]restart[/green]     Gracefully drain + relaunch (daemon-aware)
  [green]stop[/green]        Stop a running gateway instance
  [green]status[/green]      Check gateway and daemon status
  [green]doctor[/green]      Validate channel credentials (pre-flight check)
  [green]test[/green]        One-shot readiness (probes + shell + optional turn)
  [green]channels[/green]    List channels from gateway.yaml (use --probe to check creds)
  [green]diagnostics[/green] Export a pre-sanitised support bundle (diagnostics export)
  [green]send[/green]        Send a test message to a channel
  [green]hooks[/green]       Manage inbound trigger hooks (add | list | remove)
  [green]install[/green]     Install as OS daemon service
  [green]uninstall[/green]   Uninstall daemon service
  [green]logs[/green]        Show daemon service logs
  [green]mint-link[/green]   Generate a one-time magic link (options: --ttl, --host, --port)

[bold]Production Start Flags:[/bold]
  --reliability {production,default,off}  --max-concurrent-runs N  --queue-depth N
  --overflow-policy {reject,queue,shed_oldest}  --drain-timeout S
  --scale-to-zero --idle-minutes N  --identity-store PATH  --drain-marker PATH
  --watchdog [--watchdog-timeout S]

[bold]Multi-Bot Mode:[/bold]
  praisonai gateway start --config gateway.yaml

[bold]Standard Mode:[/bold]
  praisonai gateway start
  praisonai gateway start --agents agents.yaml --port 9000

[bold]Check Status:[/bold]
  praisonai gateway status

[bold]Channel Management:[/bold]
  praisonai gateway doctor --config gateway.yaml
  praisonai gateway channels --config gateway.yaml --probe
  praisonai gateway send --config gateway.yaml --channel telegram --channel-id 12345 -m "test"
"""
        try:
            from rich import print as rprint
            rprint(help_text)
        except ImportError:
            import re
            plain = re.sub(r'\\[/?[^\\]]+\\]', '', help_text)
            print(plain)
