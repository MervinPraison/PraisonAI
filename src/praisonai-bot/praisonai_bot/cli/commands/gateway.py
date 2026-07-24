"""
Gateway command group for PraisonAI CLI.

Provides commands for managing the WebSocket gateway with multi-bot support.
"""

from typing import Optional

import typer

app = typer.Typer(
    help="Manage the PraisonAI Gateway server",
    no_args_is_help=True,
)


@app.command("start")
def gateway_start(
    host: str = typer.Option("127.0.0.1", "--host", help="Host to bind to"),
    port: Optional[int] = typer.Option(None, "--port", help="Port to listen on"),
    agents: Optional[str] = typer.Option(None, "--agents", help="Path to agent configuration file"),
    config: Optional[str] = typer.Option(None, "--config", help="Path to gateway.yaml for multi-bot mode"),
    preflight: bool = typer.Option(
        True,
        "--preflight/--no-preflight",
        help="Validate channel credentials before starting (fail fast on bad tokens)",
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
):
    """Start the gateway server.

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
            results = asyncio.run(_probe_channels(channels))
            all_ok = _render_probe_results(results)
            if not all_ok:
                # An SSL certificate-verify failure (corporate proxy / MITM)
                # is NOT a credential problem — the same token connects fine at
                # runtime (#2845). Only hard-abort when a *non-SSL* channel
                # failed; otherwise warn and proceed so the runtime adapter can
                # connect, matching --no-preflight behavior.
                non_ssl_failures = any(
                    not getattr(r, "ok", False) and not _is_ssl_error(r)
                    for r in results.values()
                )
                if non_ssl_failures:
                    print(
                        "\nPre-flight check failed — aborting start. "
                        "Fix the channel credentials above or pass --no-preflight to skip."
                    )
                    raise typer.Exit(1)
                print(
                    "\nPre-flight found SSL certificate-verify failures only "
                    "(likely a proxy/MITM network). Tokens may still be valid — "
                    "continuing start. Set SSL_CERT_FILE / REQUESTS_CA_BUNDLE / "
                    "PRAISONAI_SSL_CA_BUNDLE to your corporate CA, or pass "
                    "--no-preflight to skip this check."
                )

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
    drain_timeout: float = typer.Option(
        10.0, "--drain-timeout",
        help="Seconds to wait for in-flight agent turns to finish before relaunch",
    ),
):
    """Gracefully drain in-flight turns, then relaunch the gateway.

    Daemon-aware: if the gateway is installed as an OS service
    (launchd / systemd / scheduled task), the service manager restarts it so
    operators never hand-copy ``launchctl kickstart`` / ``systemctl --user
    restart`` / ``schtasks`` per platform, preserving the installed unit's
    launch arguments. Otherwise it drains the running PID and relaunches
    directly (#3161).

    Note: the direct (non-service) relaunch cannot recover CLI-only flags the
    original process was started with (e.g. ``--openai-api``,
    ``--max-concurrent-runs``); put production settings in ``gateway.yaml`` (or
    install as a service) so a restart preserves them.

    Examples:
        praisonai gateway restart
        praisonai gateway restart --config gateway.yaml
        praisonai gateway restart --drain-timeout 30
    """
    import os
    from praisonai_bot.daemon import restart_daemon, get_daemon_status
    from ..features.gateway import GatewayHandler
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

    # Direct path: gracefully stop the running gateway (honouring drain), then
    # start a fresh instance in the foreground. The requested drain window is
    # applied to the OLD process too, so a long --drain-timeout is not cut off
    # by a fixed 10s wait before force-kill (#3161).
    handler = GatewayHandler()
    handler.stop(host=host, port=port, force=False, drain_timeout=drain_timeout)

    output.print_info("Relaunching gateway...")
    handler.start(
        host=host,
        port=port,
        agent_file=agents,
        config_file=config,
        drain_timeout=drain_timeout,
    )


@app.command("status")
def gateway_status(
    host: str = typer.Option("127.0.0.1", "--host", help="Gateway host"),
    port: Optional[int] = typer.Option(None, "--port", help="Gateway port"),
    daemon_only: bool = typer.Option(False, "--daemon-only", help="Show only daemon status"),
):
    """Check gateway status and daemon service status.

    Examples:
        praisonai gateway status
        praisonai gateway status --port 9000
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
            handler.status(host=host, port=port)
        except Exception as e:
            output.print_error(f"Error checking gateway server status: {str(e)}")


def _check_gateway_secret_strength(config_path: str):
    """Inspect the gateway's own auth_token for known-weak/placeholder values.

    Returns an actionable error string when the gateway is on an EXTERNAL bind
    and its resolved ``auth_token`` is either missing or a known-weak/
    placeholder value (caller should fail closed, mirroring startup). On a
    loopback bind a warning is printed for a weak token and ``None`` is returned
    (consistent with the permissive-loopback posture). Returns ``None`` when the
    token is strong, absent on a loopback bind, or the config cannot be read.
    """
    import os
    import yaml

    if not os.path.exists(config_path):
        return None

    try:
        with open(config_path) as fh:
            cfg = yaml.safe_load(fh) or {}
    except Exception:  # pragma: no cover — defensive
        return None

    gw = cfg.get("gateway", cfg) or {}
    raw_token = gw.get("auth_token") or os.environ.get("GATEWAY_AUTH_TOKEN", "")
    token = _resolve_env_token(raw_token) if raw_token else ""

    from praisonaiagents.gateway.protocols import (
        is_weak_secret,
        resolve_auth_mode,
        WeakGatewaySecretError,
    )

    # A strong, present token needs no further checks.
    if token and not is_weak_secret(token):
        return None

    bind_host = gw.get("bind_host") or gw.get("host") or "127.0.0.1"
    is_local = resolve_auth_mode(str(bind_host)) == "local"

    # Absent token: only a concern on an external bind, where startup fails
    # closed for a missing required secret. Doctor must agree (#3259).
    if not token:
        if is_local:
            return None
        return (
            f"Refusing to start: gateway.auth_token is required for external "
            f"bind {bind_host} but is missing.\n"
            f"Fix:  praisonai onboard         (30 seconds, 3 prompts)\n"
            f'Or:   export GATEWAY_AUTH_TOKEN="$(openssl rand -hex 16)"'
        )

    # Present-but-weak token: warn on loopback, fail closed externally.
    if is_local:
        print(
            f"⚠  gateway.auth_token is a known-weak/placeholder value "
            f"(loopback bind {bind_host}). Rotate before exposing externally."
        )
        return None

    return str(WeakGatewaySecretError(field="gateway.auth_token"))


from praisonai_bot.gateway.preflight import (  # noqa: E402 — re-exported for tests/CLI
    apply_probe_ca_bundle as _apply_probe_ca_bundle,
    check_gateway_running as _check_gateway_running,
    probe_channels as _probe_channels,
    probe_results_to_dict as _probe_results_to_dict,
    resolve_env_token as _resolve_env_token,
    run_shell_readiness_check as _run_shell_readiness_check,
    run_turn_test as _run_gateway_turn_test,
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
):
    """Validate every configured channel's credentials (pre-flight check).

    Probes each channel's token and surfaces the bot identity
    (Telegram getMe, Slack auth.test, Discord identify, WhatsApp token check)
    without starting message processing. Exits non-zero if any channel fails.

    Optional ``--turn`` runs an offline inbound agent turn via
    ``BotSessionManager.chat`` (including ``allow_shell`` setup). It does
    **not** exercise Slack Bolt/socket handlers or @mention routing.

    Examples:
        praisonai gateway doctor
        praisonai gateway doctor --config my-gateway.yaml --json
        praisonai gateway doctor --config gateway.yaml --channel slack --turn "Say OK"
    """
    import asyncio
    import json

    gateway_secret_error = _check_gateway_secret_strength(config)
    channels = _load_channels(config)

    if not channels:
        payload: dict = {"probes": {}}
        if gateway_secret_error:
            payload["gateway_auth_token"] = "weak"
        if json_output:
            print(json.dumps(payload, indent=2))
        else:
            print("No channels configured.")
            if gateway_secret_error:
                print(gateway_secret_error)
        if gateway_secret_error:
            raise typer.Exit(1)
        raise typer.Exit(0)

    availability = _compute_secret_availability(channels)
    results = asyncio.run(_probe_channels(channels))
    all_ok = all(getattr(r, "ok", False) for r in results.values())
    turn_gate_ok = all_ok
    if channel and channel in results:
        turn_gate_ok = getattr(results[channel], "ok", False)

    payload: dict = {"probes": _probe_results_to_dict(results)}
    if availability:
        payload["secrets"] = availability
    if gateway_secret_error:
        payload["gateway_auth_token"] = "weak"

    if not json_output:
        _print_secret_availability(availability)
        _render_probe_results(results, json_output=False)
        if gateway_secret_error:
            print(gateway_secret_error)

    if gateway_secret_error:
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
):
    """One-shot gateway readiness check (probes + shell wiring + optional turn).

    Recommended onboarding path before ``gateway start``. Combines credential
    probes, offline shell wiring validation, and an optional offline agent turn.

    ``--turn`` uses ``BotSessionManager.chat`` only — it does not prove live
    Slack @mention delivery. After starting, confirm ``@mention received`` in
    gateway logs.

    Examples:
        praisonai gateway test --config bot.yaml
        praisonai gateway test --config bot.yaml --channel slack --turn "Say OK"
        praisonai gateway test --config bot.yaml --check-running
    """
    import asyncio
    import json

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

    if check_running:
        running_ok, running_msg = _check_gateway_running(config)
        payload["running"] = {"ok": running_ok, "message": running_msg}
        if not json_output:
            mark = "✓" if running_ok else "✗"
            print(f"gateway up    {mark}  {running_msg}")
        failed = failed or not running_ok

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
