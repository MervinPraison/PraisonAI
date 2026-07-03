"""
Gateway CLI commands for PraisonAI.

Provides CLI commands for managing the WebSocket gateway.
"""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path
from typing import Dict, Optional

logger = logging.getLogger(__name__)

# Restart-intent exit-code protocol (Issue #2437). Source of truth lives in
# core; fall back to the sysexits.h values only when running against an older
# core that predates the protocol. We import the gateway package first and read
# the symbols off it, so a genuinely broken core install (an ImportError raised
# *while importing* praisonaiagents.gateway) still surfaces instead of being
# silently masked by the fallback — only the absence of the new symbols
# (AttributeError) triggers the compatibility shims.


def _gateway_exit_protocol_fallbacks():
    """Build the (constants, FatalConfigError, classifier) fallback tuple."""
    ok, restart, fatal = 0, 75, 78

    class FatalConfigError(Exception):
        """Fallback fatal-config error when core lacks the protocol."""

    def classify_exit_reason(exc):
        if exc is None or isinstance(exc, KeyboardInterrupt):
            return ok
        if isinstance(exc, FatalConfigError):
            return fatal
        return restart

    return ok, restart, fatal, FatalConfigError, classify_exit_reason


try:
    import praisonaiagents.gateway as _gw

    GATEWAY_OK_EXIT_CODE = _gw.GATEWAY_OK_EXIT_CODE
    GATEWAY_RESTART_EXIT_CODE = _gw.GATEWAY_RESTART_EXIT_CODE
    GATEWAY_FATAL_CONFIG_EXIT_CODE = _gw.GATEWAY_FATAL_CONFIG_EXIT_CODE
    FatalConfigError = _gw.FatalConfigError
    classify_exit_reason = _gw.classify_exit_reason
except (ModuleNotFoundError, AttributeError):  # pragma: no cover - old/absent core
    (
        GATEWAY_OK_EXIT_CODE,
        GATEWAY_RESTART_EXIT_CODE,
        GATEWAY_FATAL_CONFIG_EXIT_CODE,
        FatalConfigError,
        classify_exit_reason,
    ) = _gateway_exit_protocol_fallbacks()


def _load_praisonai_env_file() -> Dict[str, str]:
    """Load ``~/.praisonai/.env`` into ``os.environ`` (without overwriting).

    Daemons launched by ``launchd`` / ``systemd`` don't inherit the user's
    shell env and don't auto-source dotfiles, so secrets written by
    ``praisonai onboard`` (e.g. ``TELEGRAM_BOT_TOKEN``) are missing when
    the gateway starts in the background. We load them here so the
    YAML ``${VAR}`` substitution in ``GatewayServer.load_gateway_config``
    resolves correctly.

    Existing ``os.environ`` values take precedence (so user-set shell
    vars always win). Returns the dict of keys we loaded (for logging).
    """
    env_path = Path(os.environ.get("PRAISONAI_ENV_FILE")
                    or (Path.home() / ".praisonai" / ".env"))
    loaded: Dict[str, str] = {}
    if not env_path.exists():
        return loaded
    try:
        for raw in env_path.read_text().splitlines():
            s = raw.strip()
            if not s or s.startswith("#") or "=" not in s:
                continue
            k, v = s.split("=", 1)
            k = k.strip()
            v = v.strip().strip('"').strip("'")
            if not k:
                continue
            if k in os.environ:
                continue  # don't clobber existing env
            os.environ[k] = v
            loaded[k] = v
    except OSError as exc:
        logger.warning("Could not read %s: %s", env_path, exc)
    if loaded:
        logger.info(
            "Loaded %d env var(s) from %s: %s",
            len(loaded), env_path, ", ".join(sorted(loaded.keys())),
        )
    return loaded


class GatewayHandler:
    """Handler for gateway CLI commands."""
    
    def __init__(self):
        self._gateway = None
    
    def start(
        self,
        host: str = "127.0.0.1",
        port: int = 8765,
        agent_file: Optional[str] = None,
        config_file: Optional[str] = None,
        drain_timeout: Optional[float] = None,
        max_concurrent_runs: Optional[int] = None,
        queue_depth: Optional[int] = None,
        overflow_policy: Optional[str] = None,
        reliability: Optional[str] = None,
    ) -> int:
        """Start the gateway server.

        Returns a supervisor-friendly exit code (Issue #2437):

        * ``0`` — clean shutdown (Ctrl+C / SIGTERM drain).
        * ``75`` (``EX_TEMPFAIL``) — transient failure; ask the supervisor
          to restart.
        * ``78`` (``EX_CONFIG``) — fatal configuration error (bad/missing
          ``gateway.yaml``, no platforms, duplicate token); the supervisor
          should stop restarting so the operator can fix the config.

        Args:
            host: Host to bind to
            port: Port to listen on
            agent_file: Optional path to agent configuration file
            config_file: Optional path to gateway.yaml for multi-bot mode
            drain_timeout: Optional graceful-drain window in seconds (#2375).
                Overrides any ``gateway.drain_timeout`` in the YAML config.
                ``0`` disables; ``None`` falls back to the config value.
            max_concurrent_runs: Optional gateway-wide ceiling on concurrent
                agent runs (#2454). Overrides ``gateway.max_concurrent_runs``.
                ``0`` disables; ``None`` falls back to the config value.
            queue_depth: Optional bounded wait-queue depth (#2454). Overrides
                ``gateway.queue_depth``.
            overflow_policy: Optional overflow behaviour when the queue is full
                (#2454): ``reject`` | ``queue`` | ``shed_oldest``. Overrides
                ``gateway.overflow_policy``.
            reliability: Optional named reliability posture (#2531):
                ``production`` | ``default`` | ``off``. Composes graceful drain
                + inbound admission in one switch. Overrides
                ``gateway.reliability``; explicit ``--drain-timeout`` /
                ``--max-concurrent-runs`` still win.
        """
        # Ensure INFO-level logs surface to bot-stdout.log / bot-stderr.log
        # when running under launchd / systemd. Many key lifecycle events
        # (bot start, channel routing, scheduler tick, retries) are already
        # emitted via `logger.info()` — they just weren't visible with the
        # default WARNING root level. Only configure if nothing is set yet,
        # so users/embedders keep control.
        _root = logging.getLogger()
        if not _root.handlers:
            logging.basicConfig(
                level=logging.INFO,
                format="%(asctime)s %(name)s %(levelname)s %(message)s",
            )
        if _root.level > logging.INFO or _root.level == logging.NOTSET:
            _root.setLevel(logging.INFO)

        # Load ~/.praisonai/.env BEFORE any config parsing or ${VAR}
        # substitution — daemons don't inherit shell env.
        _load_praisonai_env_file()
        logger.info(
            "Gateway starting (host=%s port=%s config=%s agents=%s)",
            host, port, config_file or "-", agent_file or "-",
        )
        try:
            from praisonai_bot.gateway import WebSocketGateway
            from praisonaiagents.gateway import GatewayConfig
        except ImportError as e:
            # Missing optional deps is a config/setup problem the operator
            # must fix; restarting won't help (#2437).
            print(f"Error: Gateway requires additional dependencies. {e}")
            print("Install with: pip install praisonai[api]")
            return GATEWAY_FATAL_CONFIG_EXIT_CODE

        # Multi-bot mode: load from gateway.yaml
        if config_file:
            config = GatewayConfig(host=host, port=port)
            self._gateway = WebSocketGateway(config=config)
            # CLI --drain-timeout overrides gateway.drain_timeout in YAML (#2375)
            if drain_timeout is not None:
                self._gateway._drain_timeout_override = drain_timeout
            # CLI admission-control flags override gateway.* in YAML (#2454)
            if max_concurrent_runs is not None:
                self._gateway._max_concurrent_runs_override = max_concurrent_runs
            if queue_depth is not None:
                self._gateway._queue_depth_override = queue_depth
            if overflow_policy is not None:
                self._gateway._overflow_policy_override = overflow_policy
            # CLI --reliability preset overrides gateway.reliability in YAML (#2531)
            if reliability is not None:
                self._gateway._reliability_override = reliability
            print(f"Loading gateway config from {config_file}")
            try:
                asyncio.run(self._gateway.start_with_config(config_file))
            except KeyboardInterrupt:
                print("\nStopping gateway...")
                asyncio.run(self._gateway.stop_channels(drain_timeout=drain_timeout))
                asyncio.run(self._gateway.stop(drain_timeout=drain_timeout))
                return GATEWAY_OK_EXIT_CODE
            except FatalConfigError as e:
                # Duplicate token, no platforms, invalid credentials, etc.
                print(f"Fatal config error: {e}")
                return GATEWAY_FATAL_CONFIG_EXIT_CODE
            except (FileNotFoundError, ValueError) as e:
                # A missing, malformed, or schema-invalid gateway.yaml is
                # unrecoverable until an operator fixes it. ``load_gateway_config``
                # raises ``ValueError`` for empty/non-dict YAML, a missing
                # ``agents``/``channels`` section, or a missing channel token —
                # all fatal-config conditions that must not crash-loop (#2437).
                print(f"Fatal config error: {e}")
                return GATEWAY_FATAL_CONFIG_EXIT_CODE
            except Exception as e:
                print(f"Error starting gateway: {e}")
                return classify_exit_reason(e)
            return GATEWAY_OK_EXIT_CODE

        # Standard WebSocket-only mode
        config = GatewayConfig(host=host, port=port)
        self._gateway = WebSocketGateway(config=config)
        # Resolved graceful-drain window for this no-config run. Defaults to the
        # explicit ``--drain-timeout`` (``None`` → gateway default) and is
        # replaced below by the ``--reliability`` preset's drain when a preset
        # is selected, so the shutdown path honours the preset window (#2531).
        resolved_drain_timeout: Optional[float] = drain_timeout
        # CLI admission-control flags also apply in no-config mode (#2454):
        # build a shared gate directly so `--max-concurrent-runs` is honoured
        # even without a gateway.yaml. A ``--reliability`` preset (#2531) can
        # supply the admission ceiling too, so build the gate whenever either
        # is given, letting the preset fill fields the explicit flags omit.
        if max_concurrent_runs is not None or reliability is not None:
            try:
                from praisonai_bot.bots._admission import build_admission_gate
                from praisonai_bot.bots._reliability import resolve_reliability

                # Pass the explicit ``--drain-timeout`` through so it still wins
                # over the preset; capture the resolved window for shutdown so
                # ``--reliability production`` actually drains (#2531).
                _resolved = resolve_reliability(
                    reliability,
                    drain_timeout=drain_timeout,
                    max_concurrent_runs=max_concurrent_runs or 0,
                    queue_depth=queue_depth or 0,
                    overflow_policy=overflow_policy or "reject",
                )
                resolved_drain_timeout = _resolved.drain_timeout
                self._gateway._admission_gate = build_admission_gate(
                    max_concurrent_runs=_resolved.max_concurrent_runs,
                    queue_depth=_resolved.queue_depth,
                    overflow_policy=_resolved.overflow_policy,
                )
            except Exception as e:
                # Invalid admission-control config is unrecoverable until the
                # operator fixes it; restarting won't help (#2437).
                print(f"Error: invalid admission-control config: {e}")
                return GATEWAY_FATAL_CONFIG_EXIT_CODE


        if agent_file:
            try:
                self._load_agents_from_file(agent_file)
            except FatalConfigError as e:
                # A missing/malformed --agents file means the gateway would
                # start serving no agents while looking healthy to a
                # supervisor. Treat it as fatal-config so it stops, not
                # crash-loops, until the operator fixes it (#2437).
                print(f"Fatal config error: {e}")
                return GATEWAY_FATAL_CONFIG_EXIT_CODE

        print(f"Starting gateway on ws://{host}:{port}")
        print("Press Ctrl+C to stop")

        try:
            asyncio.run(self._gateway.start())
        except KeyboardInterrupt:
            print("\nStopping gateway...")
            # Honour the resolved graceful-drain window (explicit --drain-timeout
            # or the --reliability preset) so a no-config restart doesn't cut
            # in-flight turns (#2531). ``None`` falls back to the stop default.
            if resolved_drain_timeout is not None:
                asyncio.run(self._gateway.stop(drain_timeout=resolved_drain_timeout))
            else:
                asyncio.run(self._gateway.stop())
            return GATEWAY_OK_EXIT_CODE
        except FatalConfigError as e:
            print(f"Fatal config error: {e}")
            return GATEWAY_FATAL_CONFIG_EXIT_CODE
        except Exception as e:
            print(f"Error starting gateway: {e}")
            return classify_exit_reason(e)
        return GATEWAY_OK_EXIT_CODE
    
    def _load_agents_from_file(self, file_path: str) -> None:
        """Load agents from a configuration file.

        Raises:
            FatalConfigError: If the file is missing, unreadable, malformed,
                or contains no usable ``agents`` section. A broken ``--agents``
                file is unrecoverable until fixed, so it must surface (#2437)
                rather than silently starting an empty gateway.
        """
        import os
        import yaml

        if not os.path.exists(file_path):
            raise FatalConfigError(f"Agent file not found: {file_path}")

        try:
            with open(file_path, "r") as f:
                config = yaml.safe_load(f)
        except (OSError, yaml.YAMLError) as e:
            raise FatalConfigError(f"Could not read agent file {file_path}: {e}")

        if not isinstance(config, dict) or not config.get("agents"):
            raise FatalConfigError(
                f"Agent file {file_path} has no 'agents' section"
            )

        from praisonaiagents import Agent

        agents = config["agents"]
        if not isinstance(agents, list):
            raise FatalConfigError(
                f"Agent file {file_path} 'agents' section must be a list"
            )

        for agent_config in agents:
            if not isinstance(agent_config, dict):
                raise FatalConfigError(
                    f"Agent file {file_path} contains a non-mapping agent entry"
                )
            agent = Agent(
                name=agent_config.get("name", "agent"),
                instructions=agent_config.get("instructions", ""),
                llm=agent_config.get("llm"),
            )
            agent_id = self._gateway.register_agent(agent)
            print(f"Registered agent: {agent_id}")
    
    def stop(self, host: str = "127.0.0.1", port: int = 8765, force: bool = False) -> None:
        """Stop a running gateway instance.
        
        Args:
            host: Gateway host
            port: Gateway port 
            force: Force stop (kill process)
        """
        try:
            from praisonai_bot.gateway.port_utils import GatewayPIDLock
        except ImportError as e:
            print(f"Error: Gateway utilities not available. {e}")
            return
        
        pid_lock = GatewayPIDLock(host=host, port=port)
        lock_info = pid_lock.get_lock_info()
        
        if not lock_info:
            print(f"No gateway PID lock found. Gateway may not be running on {host}:{port}")
            return
        
        pid = lock_info['pid']
        is_running = lock_info['is_running']
        
        if not is_running:
            print(f"Gateway process (PID {pid}) is no longer running. Cleaning up stale lock.")
            pid_lock.release_lock()
            return
        
        if force:
            self._force_kill_process(pid)
        else:
            self._graceful_stop_process(pid)
        
        # Clean up lock file
        pid_lock.release_lock()
        print(f"Gateway stopped (PID {pid})")
    
    def _graceful_stop_process(self, pid: int) -> None:
        """Gracefully stop a process by sending SIGTERM."""
        import signal
        import time
        import os
        
        try:
            print(f"Sending stop signal to PID {pid}...")
            os.kill(pid, signal.SIGTERM)
            
            # Wait up to 10 seconds for graceful shutdown
            for _ in range(100):
                try:
                    os.kill(pid, 0)  # Check if process exists
                    time.sleep(0.1)
                except (OSError, ProcessLookupError):
                    return  # Process has stopped
            
            print(f"Process {pid} did not stop gracefully, forcing...")
            self._force_kill_process(pid)
            
        except (OSError, ProcessLookupError):
            print(f"Process {pid} not found or already stopped")
    
    def _force_kill_process(self, pid: int) -> None:
        """Force kill a process with SIGKILL (Windows: SIGTERM)."""
        import signal
        import os
        import sys
        
        try:
            print(f"Force killing PID {pid}...")
            # Use SIGTERM on Windows since SIGKILL is not available
            sig = signal.SIGTERM if sys.platform == "win32" else signal.SIGKILL
            os.kill(pid, sig)
        except (OSError, ProcessLookupError):
            print(f"Process {pid} not found or already stopped")

    def hooks(self, args) -> int:
        """Manage inbound trigger hooks in a gateway.yaml file (Issue #2281).

        Sub-actions: ``add``, ``list``, ``remove``. Edits the ``hooks:`` section
        of ``gateway.yaml`` so the trigger surface is declarable from the CLI,
        consistent with the YAML and Python surfaces.
        """
        import yaml

        action = getattr(args, "hooks_command", None)
        config_path = getattr(args, "config_file", None) or "gateway.yaml"

        def _load() -> Dict:
            if os.path.exists(config_path):
                try:
                    with open(config_path, "r") as f:
                        data = yaml.safe_load(f) or {}
                    if not isinstance(data, dict):
                        print(
                            f"Error: {config_path} must contain a YAML mapping at the root."
                        )
                        return {}
                    return data
                except Exception as e:
                    print(f"Error reading {config_path}: {e}")
                    return {}
            return {}

        def _save(cfg: Dict) -> None:
            with open(config_path, "w") as f:
                yaml.safe_dump(cfg, f, default_flow_style=False, sort_keys=False)

        cfg = _load()
        hooks = cfg.get("hooks") or []
        if not isinstance(hooks, list):
            hooks = []

        if action == "list":
            if not hooks:
                print(f"No hooks configured in {config_path}")
                return 0
            print(f"Hooks in {config_path}:")
            for h in hooks:
                if isinstance(h, dict):
                    print(
                        f"  POST /hooks/{h.get('path')}  "
                        f"-> agent={h.get('agent') or '<default>'} "
                        f"deliver_to={h.get('deliver_to') or '-'}"
                    )
            return 0

        if action == "remove":
            path = getattr(args, "path", None)
            if not path:
                print("Error: hook path required")
                return 1
            path = path.strip().strip("/")
            new_hooks = [
                h for h in hooks
                if not (isinstance(h, dict) and h.get("path") == path)
            ]
            if len(new_hooks) == len(hooks):
                print(f"No hook '{path}' found in {config_path}")
                return 1
            cfg["hooks"] = new_hooks
            _save(cfg)
            print(f"Removed hook '{path}' from {config_path}")
            return 0

        if action == "add":
            path = getattr(args, "path", None)
            if not path:
                print("Error: hook path required (e.g. 'gmail')")
                return 1
            path = path.strip().strip("/")
            entry: Dict = {"path": path}
            if getattr(args, "agent", None):
                entry["agent"] = args.agent
            if getattr(args, "action_type", None):
                entry["action"] = args.action_type
            if getattr(args, "auth", None):
                entry["auth"] = args.auth
            if getattr(args, "session_key", None):
                entry["session_key"] = args.session_key
            if getattr(args, "idempotency_key", None):
                entry["idempotency_key"] = args.idempotency_key
            if getattr(args, "deliver_to", None):
                entry["deliver_to"] = args.deliver_to
            if getattr(args, "message", None):
                entry["message"] = args.message

            # Replace any existing hook on the same path.
            hooks = [
                h for h in hooks
                if not (isinstance(h, dict) and h.get("path") == path)
            ]
            hooks.append(entry)
            cfg["hooks"] = hooks
            _save(cfg)
            print(f"Added hook 'POST /hooks/{path}' to {config_path}")
            return 0

        print("Usage: praisonai gateway hooks {add|list|remove} ...")
        return 1

    def status(self, host: str = "127.0.0.1", port: int = 8765) -> None:
        """Check gateway status.
        
        Args:
            host: Gateway host
            port: Gateway port
        """
        import urllib.request
        import json
        
        # Check PID lock info first
        try:
            from praisonai_bot.gateway.port_utils import GatewayPIDLock, is_port_in_use
            pid_lock = GatewayPIDLock(host=host, port=port)
            lock_info = pid_lock.get_lock_info()
            
            if lock_info:
                pid = lock_info['pid']
                is_running = lock_info['is_running']
                lock_host = lock_info['host']
                lock_port = lock_info['port']
                
                if is_running:
                    print(f"Gateway PID lock: Process {pid} running ({lock_host}:{lock_port})")
                else:
                    print(f"Gateway PID lock: Stale lock (process {pid} not running)")
            else:
                print("Gateway PID lock: No lock file found")
            
            # Check if port is in use
            if is_port_in_use(host, port):
                print(f"Port {host}:{port}: In use")
            else:
                print(f"Port {host}:{port}: Available")
                
        except ImportError:
            print("PID lock status: Utilities not available")
        
        # Try to connect to health endpoint
        url = f"http://{host}:{port}/health"
        
        try:
            with urllib.request.urlopen(url, timeout=5) as response:
                data = json.loads(response.read().decode())
                print(f"Gateway Status: {data.get('status', 'unknown')}")
                print(f"  Uptime: {data.get('uptime', 0):.1f}s")
                print(f"  Agents: {data.get('agents', 0)}")
                print(f"  Sessions: {data.get('sessions', 0)}")
                print(f"  Clients: {data.get('clients', 0)}")
        except Exception as e:
            print(f"Gateway not reachable at {url}")
            print(f"Error: {e}")


def handle_gateway_command(args) -> int:
    """Handle gateway CLI command.
    
    Now uses the unified configuration schema for all bot/gateway operations.
    
    Args:
        args: List of CLI arguments (from main.py unknown_args) or argparse Namespace.
    """
    import argparse
    
    if isinstance(args, list):
        parser = argparse.ArgumentParser(
            prog="praisonai gateway",
            description="Manage the PraisonAI Gateway server",
        )
        subparsers = parser.add_subparsers(dest="gateway_command", help="Gateway commands")
        
        # start subcommand
        start_parser = subparsers.add_parser("start", help="Start the gateway server")
        start_parser.add_argument("--host", default="127.0.0.1", help="Host to bind to (default: 127.0.0.1)")
        start_parser.add_argument("--port", type=int, default=8765, help="Port to listen on (default: 8765)")
        start_parser.add_argument("--agents", help="Path to agent configuration file")
        start_parser.add_argument("--config", dest="config_file", help="Path to gateway.yaml for multi-bot mode")
        start_parser.add_argument(
            "--drain-timeout", dest="drain_timeout", type=float, default=None,
            help="Seconds to wait for in-flight agent turns to finish on shutdown (0 disables; #2375)",
        )
        start_parser.add_argument(
            "--max-concurrent-runs", dest="max_concurrent_runs", type=int, default=None,
            help="Gateway-wide ceiling on simultaneously-running agent turns (0 disables; #2454)",
        )
        start_parser.add_argument(
            "--queue-depth", dest="queue_depth", type=int, default=None,
            help="Bounded wait queue depth when at the concurrency ceiling (#2454)",
        )
        start_parser.add_argument(
            "--overflow-policy", dest="overflow_policy", default=None,
            choices=["reject", "queue", "shed_oldest"],
            help="Behaviour when the wait queue is full (default: reject; #2454)",
        )
        start_parser.add_argument(
            "--reliability", dest="reliability", default=None,
            choices=["production", "default", "off"],
            help="Named reliability posture composing drain + admission in one "
                 "switch (#2531)",
        )
        
        # status subcommand
        status_parser = subparsers.add_parser("status", help="Check gateway status")
        status_parser.add_argument("--host", default="127.0.0.1", help="Gateway host (default: 127.0.0.1)")
        status_parser.add_argument("--port", type=int, default=8765, help="Gateway port (default: 8765)")

        # hooks subcommand — manage inbound trigger hooks (Issue #2281)
        hooks_parser = subparsers.add_parser(
            "hooks", help="Manage inbound trigger hooks (POST /hooks/<path>)"
        )
        hooks_sub = hooks_parser.add_subparsers(
            dest="hooks_command", help="Hook commands"
        )

        hooks_add = hooks_sub.add_parser("add", help="Add a hook to gateway.yaml")
        hooks_add.add_argument("path", help="Hook path, e.g. 'gmail' -> POST /hooks/gmail")
        hooks_add.add_argument("--agent", help="Agent id to run (default: first agent)")
        hooks_add.add_argument(
            "--action", dest="action_type", default="agent",
            choices=["agent", "wake"], help="agent runs a turn, wake nudges a session",
        )
        hooks_add.add_argument("--auth", help="Bearer token / shared secret for this hook")
        hooks_add.add_argument("--session-key", dest="session_key", help="Session key template")
        hooks_add.add_argument(
            "--idempotency-key", dest="idempotency_key", help="Idempotency key template",
        )
        hooks_add.add_argument("--deliver-to", dest="deliver_to", help="channel:target for the reply")
        hooks_add.add_argument("--message", help="Message template from the payload")
        hooks_add.add_argument(
            "--config", dest="config_file", default="gateway.yaml",
            help="Path to gateway.yaml (default: gateway.yaml)",
        )

        hooks_list = hooks_sub.add_parser("list", help="List configured hooks")
        hooks_list.add_argument(
            "--config", dest="config_file", default="gateway.yaml",
            help="Path to gateway.yaml (default: gateway.yaml)",
        )

        hooks_remove = hooks_sub.add_parser("remove", help="Remove a hook")
        hooks_remove.add_argument("path", help="Hook path to remove")
        hooks_remove.add_argument(
            "--config", dest="config_file", default="gateway.yaml",
            help="Path to gateway.yaml (default: gateway.yaml)",
        )

        try:
            args = parser.parse_args(args)
        except SystemExit:
            return 1
    
    handler = GatewayHandler()
    
    subcommand = getattr(args, "gateway_command", None) or "start"
    
    if subcommand == "start":
        # Propagate the supervisor-friendly exit code from start() (#2437):
        # 0 clean, 75 transient/restart, 78 fatal-config/do-not-restart.
        return handler.start(
            host=getattr(args, "host", "127.0.0.1"),
            port=getattr(args, "port", 8765),
            agent_file=getattr(args, "agents", None),
            config_file=getattr(args, "config_file", None),
            drain_timeout=getattr(args, "drain_timeout", None),
            max_concurrent_runs=getattr(args, "max_concurrent_runs", None),
            queue_depth=getattr(args, "queue_depth", None),
            overflow_policy=getattr(args, "overflow_policy", None),
            reliability=getattr(args, "reliability", None),
        )
    elif subcommand == "status":
        handler.status(
            host=getattr(args, "host", "127.0.0.1"),
            port=getattr(args, "port", 8765),
        )
    elif subcommand == "hooks":
        return handler.hooks(args)
    else:
        print(f"Unknown gateway command: {subcommand}")
        print("Available commands: start, status, hooks")
        return 1
    return 0
