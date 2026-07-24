"""Gateway preflight helpers — probes, shell wiring, and offline turn tests.

Shared by ``praisonai gateway doctor``, ``praisonai gateway test``, and
``praisonai doctor bots`` so probe/turn logic lives in one place (not the CLI
module).
"""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class ShellReadinessResult:
    """Outcome of offline shell wiring validation."""

    ok: bool
    message: str
    issues: List[str] = field(default_factory=list)


def load_channels_mapping(config_path: str) -> dict:
    """Load the ``channels`` mapping from a gateway/bot YAML file."""
    import yaml

    with open(config_path) as f:
        cfg = yaml.safe_load(f) or {}
    return cfg.get("channels") or {}


def resolve_gateway_endpoint(config_path: str) -> Tuple[str, int]:
    """Resolve ``(host, port)`` from config and ``GATEWAY_PORT`` env."""
    import yaml

    with open(config_path) as f:
        cfg = yaml.safe_load(f) or {}
    gateway_cfg = cfg.get("gateway") or {}
    host = str(gateway_cfg.get("host") or "127.0.0.1")
    raw_port = gateway_cfg.get("port")
    if raw_port is None:
        raw_port = os.environ.get("GATEWAY_PORT", "8765")
    try:
        port = int(raw_port)
    except (TypeError, ValueError):
        port = 8765
    return host, port


def probe_results_to_dict(results: dict) -> dict:
    """JSON-serializable per-channel probe payload."""
    return {
        name: r.to_dict() if hasattr(r, "to_dict") else vars(r)
        for name, r in results.items()
    }


def resolve_env_token(value):
    """Resolve a credential input to its value for probing."""
    if isinstance(value, dict) and "source" in value and "id" in value:
        try:
            from praisonaiagents.secrets import resolve_secret

            result = resolve_secret(value)
            return result.value or ""
        except Exception:  # pragma: no cover — defensive
            return ""
    if isinstance(value, str) and value.startswith("${") and value.endswith("}"):
        return os.environ.get(value[2:-1], "")
    return value


def apply_probe_ca_bundle() -> None:
    """Point the probe HTTP client at a custom CA bundle if configured."""
    preferred = os.environ.get("PRAISONAI_SSL_CA_BUNDLE")
    ca_bundle = (
        preferred
        or os.environ.get("REQUESTS_CA_BUNDLE")
        or os.environ.get("SSL_CERT_FILE")
    )
    if not ca_bundle:
        return

    if not os.path.exists(ca_bundle):
        print(
            f"Warning: CA bundle path '{ca_bundle}' does not exist — "
            "SSL_CERT_FILE / REQUESTS_CA_BUNDLE not updated for probe."
        )
        return

    if preferred and preferred == ca_bundle:
        os.environ["SSL_CERT_FILE"] = ca_bundle
        os.environ["REQUESTS_CA_BUNDLE"] = ca_bundle
    else:
        os.environ.setdefault("SSL_CERT_FILE", ca_bundle)
        os.environ.setdefault("REQUESTS_CA_BUNDLE", ca_bundle)


async def probe_channels(channels: dict, timeout: float = 15.0) -> dict:
    """Probe each channel's credentials without starting message processing."""
    try:
        from praisonai_bot.cli.features.gateway import _load_praisonai_env_file

        _load_praisonai_env_file()
    except Exception:  # pragma: no cover — defensive
        pass

    apply_probe_ca_bundle()

    from praisonai_bot.bots import Bot
    from praisonaiagents.bots import ProbeResult

    async def _probe_one(name: str, ch_cfg: dict):
        platform = ch_cfg.get("platform", name)
        token = resolve_env_token(ch_cfg.get("token", ""))
        extras = {
            k: resolve_env_token(v)
            for k, v in ch_cfg.items()
            if k not in ("platform", "token")
        }
        try:
            bot = Bot(platform, token=token, **extras)
            result = await asyncio.wait_for(bot.probe(), timeout=timeout)
            if str(platform).lower() == "slack" and not resolve_env_token(ch_cfg.get("app_token", "")):
                warnings = list((result.details or {}).get("warnings") or [])
                warnings.append("SLACK_APP_TOKEN missing — Socket Mode will not start")
                result.details = {**(result.details or {}), "warnings": warnings}
            return name, result
        except asyncio.TimeoutError:
            return name, ProbeResult(
                ok=False,
                platform=platform,
                error=f"probe timed out after {timeout:g}s",
            )
        except Exception as e:  # pragma: no cover — defensive
            return name, ProbeResult(ok=False, platform=platform, error=str(e))

    results = await asyncio.gather(
        *(_probe_one(name, ch_cfg or {}) for name, ch_cfg in channels.items())
    )
    return dict(results)


async def probe_channels_from_config(
    config_path: str,
    channel_filter: Optional[str] = None,
    timeout: float = 15.0,
) -> dict:
    """Load config and probe channels, optionally filtering to one channel."""
    channels = load_channels_mapping(config_path)
    if channel_filter:
        if channel_filter not in channels:
            raise ValueError(f"Channel '{channel_filter}' not found in config")
        channels = {channel_filter: channels[channel_filter]}
    return await probe_channels(channels, timeout=timeout)


def run_shell_readiness_check(config_path: str) -> ShellReadinessResult:
    """Offline validation of ``allow_shell`` wiring (no LLM, no network)."""
    import yaml
    from praisonaiagents import Agent
    from praisonaiagents.approval import get_approval_registry
    from praisonaiagents.bots.config import BotConfig
    from praisonai_bot.bots._defaults import apply_bot_smart_defaults, enable_shell_tools

    with open(config_path) as f:
        cfg = yaml.safe_load(f) or {}

    channels = cfg.get("channels") or {}
    agents_cfg = cfg.get("agents") or {}
    shell_channels = [
        name for name, ch in channels.items() if (ch or {}).get("allow_shell")
    ]

    if not shell_channels:
        return ShellReadinessResult(
            ok=True,
            message="No channels with allow_shell: true",
        )

    issues: List[str] = []
    bot_config = BotConfig()

    for channel_name in shell_channels:
        ch_cfg = dict(channels[channel_name] or {})
        ch_cfg.setdefault("platform", channel_name)
        platform = str(ch_cfg.get("platform") or channel_name).lower()

        routing = ch_cfg.get("routing") or cfg.get("routing") or {}
        agent_id = routing.get("default") or next(iter(agents_cfg), None)
        if not agent_id or agent_id not in agents_cfg:
            issues.append(f"{channel_name}: no agent configured for shell routing")
            continue

        acfg = agents_cfg[agent_id] or {}
        agent = Agent(
            name=acfg.get("name", agent_id),
            instructions=acfg.get("instructions", ""),
        )
        agent = apply_bot_smart_defaults(agent, bot_config)
        agent = enable_shell_tools(agent, bot_config, ch_cfg, channel_type=platform)

        tool_names = {
            getattr(t, "name", None) or getattr(t, "__name__", "")
            for t in (getattr(agent, "tools", None) or [])
        }
        if "execute_command" not in tool_names:
            issues.append(f"{channel_name}: execute_command not in agent tools")

        if getattr(agent, "_approval_backend", None) is None:
            issues.append(f"{channel_name}: no approval backend on agent")

        reg = get_approval_registry()
        agent_name = getattr(agent, "name", None)
        if agent_name and reg.get_backend(agent_name=agent_name) is None:
            issues.append(f"{channel_name}: approval registry not synced for agent")

    if issues:
        return ShellReadinessResult(
            ok=False,
            message=f"Shell wiring issues on {len(issues)} check(s)",
            issues=issues,
        )
    return ShellReadinessResult(
        ok=True,
        message=f"Shell wiring OK for {len(shell_channels)} channel(s)",
    )


async def run_turn_test(
    config_path: str,
    channel_name: str,
    prompt: str,
) -> Tuple[bool, str]:
    """Simulate one inbound agent turn offline via ``BotSessionManager.chat``.

    Does **not** exercise Slack Bolt/socket handlers or @mention routing — only
    the BotSessionManager path after manual shell setup.
    """
    import yaml
    from praisonaiagents import Agent
    from praisonaiagents.bots.config import BotConfig
    from praisonai_bot.bots._defaults import apply_bot_smart_defaults, enable_shell_tools
    from praisonai_bot.bots._session import BotSessionManager

    with open(config_path) as f:
        cfg = yaml.safe_load(f) or {}

    channels = cfg.get("channels") or {}
    if channel_name not in channels:
        return False, f"Channel '{channel_name}' not found in config"

    ch_cfg = dict(channels[channel_name] or {})
    ch_cfg.setdefault("platform", channel_name)

    agents_cfg = cfg.get("agents") or {}
    routing = ch_cfg.get("routing") or cfg.get("routing") or {}
    agent_id = routing.get("default")
    if not agent_id:
        agent_id = next(iter(agents_cfg), None)
    if not agent_id or agent_id not in agents_cfg:
        return False, f"No agent configured for channel '{channel_name}'"

    acfg = agents_cfg[agent_id] or {}
    agent = Agent(
        name=acfg.get("name", agent_id),
        instructions=acfg.get("instructions", ""),
        llm=acfg.get("model") or acfg.get("llm", "gpt-4o-mini"),
    )
    bot_config = BotConfig()
    agent = apply_bot_smart_defaults(agent, bot_config)
    platform = str(ch_cfg.get("platform") or channel_name).lower()
    if ch_cfg.get("allow_shell"):
        agent = enable_shell_tools(agent, bot_config, ch_cfg, channel_type=platform)

    mgr = BotSessionManager(platform=platform)
    try:
        result = await mgr.chat(
            agent,
            "gateway-doctor-test",
            prompt,
            chat_id="gateway-doctor-test",
        )
    except Exception as exc:
        return False, str(exc)

    text = str(result or "").strip()
    if not text:
        return False, "Agent returned an empty response"
    return True, text[:500]


def check_gateway_running(config_path: str, timeout: float = 5.0) -> Tuple[bool, str]:
    """Probe the gateway REST ``/info`` endpoint (advisory)."""
    import urllib.error
    import urllib.request

    host, port = resolve_gateway_endpoint(config_path)
    url = f"http://{host}:{port}/info"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            if resp.status == 200:
                return True, f"Gateway reachable at {url}"
            return False, f"Gateway returned HTTP {resp.status} at {url}"
    except urllib.error.URLError as exc:
        return False, f"Gateway not reachable at {url}: {exc.reason}"
    except Exception as exc:  # pragma: no cover — defensive
        return False, str(exc)


# ── Runtime / inbound / duplicate diagnostics (gateway test) ─────────────


@dataclass
class RuntimeProbeResult:
    """Outcome of a single HTTP runtime probe."""

    ok: bool
    status_code: Optional[int] = None
    body: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


@dataclass
class RuntimeCheckResult:
    """Combined runtime reachability check."""

    ok: bool
    host: str
    port: int
    info: RuntimeProbeResult
    health: RuntimeProbeResult
    ready: RuntimeProbeResult
    live: RuntimeProbeResult

    def to_dict(self) -> Dict[str, Any]:
        def _probe_dict(p: RuntimeProbeResult, path: str) -> Dict[str, Any]:
            return {
                "ok": p.ok,
                "path": path,
                "status_code": p.status_code,
                "error": p.error,
                "body": p.body,
            }

        return {
            "ok": self.ok,
            "host": self.host,
            "port": self.port,
            "info": _probe_dict(self.info, "/info"),
            "health": _probe_dict(self.health, "/health"),
            "ready": _probe_dict(self.ready, "/ready"),
            "live": _probe_dict(self.live, "/live"),
        }


@dataclass
class InboundCheckResult:
    """Outcome of live inbound delivery verification."""

    ok: bool
    proves: str = "inbound_delivery"
    since_seconds: float = 0.0
    mentions_in_window: int = 0
    last_mention_at: Optional[str] = None
    last_mention_text: Optional[str] = None
    no_inbound_in_window: bool = False
    metrics_inbound_total: Optional[float] = None
    metrics_inbound_delta: Optional[float] = None
    hint: Optional[str] = None
    log_path: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ok": self.ok,
            "proves": self.proves,
            "since_seconds": self.since_seconds,
            "mentions_in_window": self.mentions_in_window,
            "last_mention_at": self.last_mention_at,
            "last_mention_text": self.last_mention_text,
            "no_inbound_in_window": self.no_inbound_in_window,
            "metrics_inbound_total": self.metrics_inbound_total,
            "metrics_inbound_delta": self.metrics_inbound_delta,
            "hint": self.hint,
            "log_path": self.log_path,
        }


@dataclass
class DuplicateService:
    """A detected gateway or bot service."""

    label: str
    installed: bool = False
    running: bool = False
    pid: Optional[int] = None
    plist_path: Optional[str] = None
    token_fingerprints: Dict[str, str] = field(default_factory=dict)


@dataclass
class DuplicateCheckResult:
    """Outcome of duplicate gateway / token conflict scan."""

    ok: bool
    services: List[DuplicateService] = field(default_factory=list)
    shared_tokens: List[str] = field(default_factory=list)
    hermes_platforms: Dict[str, Any] = field(default_factory=dict)
    pid_lock: Optional[Dict[str, Any]] = None
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ok": self.ok,
            "services": [
                {
                    "label": s.label,
                    "installed": s.installed,
                    "running": s.running,
                    "pid": s.pid,
                    "plist_path": s.plist_path,
                    "token_fingerprints": s.token_fingerprints,
                }
                for s in self.services
            ],
            "shared_tokens": self.shared_tokens,
            "hermes_platforms": self.hermes_platforms,
            "pid_lock": self.pid_lock,
            "warnings": self.warnings,
        }


def default_log_path() -> str:
    """Return the default gateway stderr log path."""
    return os.path.expanduser("~/.praisonai/logs/bot-stderr.log")


def parse_since_window(since: str) -> float:
    """Parse a human duration like ``10m`` or ``2h`` into seconds."""
    raw = (since or "10m").strip().lower()
    if raw.isdigit():
        return float(raw)
    multipliers = {"s": 1, "m": 60, "h": 3600, "d": 86400}
    if len(raw) >= 2 and raw[-1] in multipliers:
        try:
            return float(raw[:-1]) * multipliers[raw[-1]]
        except ValueError:
            pass
    return 600.0


def _gateway_auth_headers(host: str) -> Dict[str, str]:
    """Build auth headers for gateway endpoints that require a token."""
    token = os.environ.get("GATEWAY_AUTH_TOKEN", "").strip()
    if not token:
        return {}
    if host in ("127.0.0.1", "localhost", "::1"):
        return {}
    return {"Authorization": f"Bearer {token}"}


def _http_get_json(
    host: str,
    port: int,
    path: str,
    timeout: float = 5.0,
    auth: bool = False,
) -> RuntimeProbeResult:
    """Fetch a JSON endpoint from the gateway."""
    import json
    import urllib.error
    import urllib.request

    url = f"http://{host}:{port}{path}"
    headers = _gateway_auth_headers(host) if auth else {}
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = json.loads(resp.read().decode())
            ok = 200 <= resp.status < 300
            if path == "/ready" and isinstance(body, dict):
                ok = ok and bool(body.get("ready", False))
            if path == "/live" and isinstance(body, dict):
                ok = ok and bool(body.get("alive", False))
            return RuntimeProbeResult(ok=ok, status_code=resp.status, body=body)
    except urllib.error.HTTPError as exc:
        body = None
        try:
            body = json.loads(exc.read().decode())
        except Exception:
            pass
        ok = False
        if path in ("/ready", "/live") and exc.code == 503:
            ok = False
        return RuntimeProbeResult(
            ok=ok,
            status_code=exc.code,
            body=body,
            error=str(exc.reason),
        )
    except Exception as exc:
        return RuntimeProbeResult(ok=False, error=str(exc))


def check_runtime(
    config_path: str,
    timeout: float = 5.0,
) -> RuntimeCheckResult:
    """Probe gateway runtime endpoints: ``/info``, ``/health``, ``/ready``, ``/live``."""
    host, port = resolve_gateway_endpoint(config_path)
    info = _http_get_json(host, port, "/info", timeout=timeout, auth=True)
    health = _http_get_json(host, port, "/health", timeout=timeout)
    ready = _http_get_json(host, port, "/ready", timeout=timeout)
    live = _http_get_json(host, port, "/live", timeout=timeout)
    ok = info.ok and health.ok and ready.ok and live.ok
    return RuntimeCheckResult(
        ok=ok,
        host=host,
        port=port,
        info=info,
        health=health,
        ready=ready,
        live=live,
    )


def _parse_log_timestamp(line: str) -> Optional[float]:
    """Best-effort parse of a log line timestamp."""
    import datetime
    import re

    match = re.match(
        r"^(\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}(?:,\d+)?)",
        line,
    )
    if not match:
        return None
    raw = match.group(1).replace(",", ".")
    for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.datetime.strptime(raw[:26], fmt).timestamp()
        except ValueError:
            continue
    return None


def parse_inbound_log(
    log_path: str,
    since_seconds: float,
    marker: str = "@mention received:",
) -> Tuple[int, Optional[str], Optional[str]]:
    """Scan a log file for inbound mention markers within a time window."""
    import time

    if not os.path.exists(log_path):
        return 0, None, None

    cutoff = time.time() - since_seconds
    count = 0
    last_at: Optional[str] = None
    last_text: Optional[str] = None

    try:
        with open(log_path, encoding="utf-8", errors="replace") as handle:
            lines = handle.readlines()
    except OSError:
        return 0, None, None

    for line in lines:
        if marker not in line:
            continue
        ts = _parse_log_timestamp(line)
        if ts is not None and ts < cutoff:
            continue
        count += 1
        if ts is not None:
            import datetime

            last_at = datetime.datetime.fromtimestamp(ts).isoformat()
        idx = line.find(marker)
        last_text = line[idx + len(marker) :].strip() if idx >= 0 else line.strip()

    return count, last_at, last_text


def _scrape_metrics_counter(
    host: str,
    port: int,
    counter: str,
    timeout: float = 5.0,
) -> Optional[float]:
    """Scrape a Prometheus counter value from ``GET /metrics``."""
    import re
    import urllib.error
    import urllib.request

    url = f"http://{host}:{port}/metrics"
    headers = _gateway_auth_headers(host)
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            text = resp.read().decode()
    except Exception:
        return None

    total = 0.0
    found = False
    pattern = re.compile(rf"^{re.escape(counter)}(?:\{{[^}}]*\}})?\s+([0-9.eE+-]+)")
    for line in text.splitlines():
        if line.startswith("#"):
            continue
        match = pattern.match(line.strip())
        if match:
            found = True
            total += float(match.group(1))
    return total if found else None


def _metrics_baseline_path() -> str:
    return os.path.expanduser("~/.praisonai/state/inbound_metrics_baseline.json")


def _load_metrics_baseline(host: str, port: int) -> Optional[Dict[str, Any]]:
    import json

    path = _metrics_baseline_path()
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
        if data.get("host") == host and int(data.get("port", -1)) == int(port):
            return data
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        pass
    return None


def _save_metrics_baseline(host: str, port: int, counter: Optional[float]) -> None:
    import json
    import time

    if counter is None:
        return
    path = _metrics_baseline_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    payload = {"host": host, "port": int(port), "counter": counter, "ts": time.time()}
    try:
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle)
    except OSError:
        pass


def _metrics_inbound_delta(
    host: str,
    port: int,
    since_seconds: float,
    timeout: float = 5.0,
) -> Tuple[Optional[float], Optional[float]]:
    """Return ``(current_total, delta_since_baseline)`` for inbound metrics."""
    import time

    current = _scrape_metrics_counter(host, port, "messages_inbound_total", timeout=timeout)
    baseline = _load_metrics_baseline(host, port)
    delta: Optional[float] = None
    if (
        baseline is not None
        and current is not None
        and baseline.get("counter") is not None
    ):
        age = time.time() - float(baseline.get("ts") or 0)
        if age <= since_seconds:
            delta = max(0.0, current - float(baseline["counter"]))
    _save_metrics_baseline(host, port, current)
    return current, delta


def _expected_bot_hint(probe_results: dict) -> Optional[str]:
    """Build expected bot identity hint from probe results."""
    for _name, probe in probe_results.items():
        if not getattr(probe, "ok", False):
            continue
        username = getattr(probe, "bot_username", None) or ""
        details = getattr(probe, "details", None) or {}
        user_id = details.get("user_id") if isinstance(details, dict) else None
        if username and user_id:
            return f"Expected bot: @{username} ({user_id})"
        if username:
            return f"Expected bot: @{username}"
    return None


def check_inbound(
    config_path: str,
    since: str = "10m",
    log_path: Optional[str] = None,
    timeout: float = 5.0,
    probe_results: Optional[dict] = None,
) -> InboundCheckResult:
    """Verify recent inbound delivery via logs and optional metrics."""
    since_seconds = parse_since_window(since)
    path = log_path or default_log_path()
    count, last_at, last_text = parse_inbound_log(path, since_seconds)

    host, port = resolve_gateway_endpoint(config_path)
    metrics_total, metrics_delta = _metrics_inbound_delta(
        host, port, since_seconds, timeout=timeout
    )

    hint = _expected_bot_hint(probe_results or {})
    no_inbound = count == 0 and not (metrics_delta and metrics_delta > 0)
    ok = count > 0 or bool(metrics_delta and metrics_delta > 0)

    if no_inbound and hint:
        hint = (
            f"{hint}. Message may have hit a different Slack app. "
            "Use --check-duplicates to scan for competing gateways."
        )
    elif no_inbound:
        hint = (
            "No @mention received in the log window. "
            "Send a Slack message to your bot, then re-run with --check-inbound."
        )

    return InboundCheckResult(
        ok=ok,
        since_seconds=since_seconds,
        mentions_in_window=count,
        last_mention_at=last_at,
        last_mention_text=last_text,
        no_inbound_in_window=no_inbound,
        metrics_inbound_total=metrics_total,
        metrics_inbound_delta=metrics_delta,
        hint=hint,
        log_path=path,
    )


def _token_fingerprint(value: str) -> Optional[str]:
    """Return a short fingerprint for a token value."""
    if not value or not str(value).strip():
        return None
    import hashlib

    return hashlib.sha256(str(value).encode()).hexdigest()[:12]


def _read_env_file_tokens(path: str) -> Dict[str, str]:
    """Read ``KEY=value`` tokens from an env file."""
    tokens: Dict[str, str] = {}
    if not os.path.exists(path):
        return tokens
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            for line in handle:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, val = line.partition("=")
                key = key.strip()
                val = val.strip().strip('"').strip("'")
                if key.endswith("_TOKEN") and val:
                    tokens[key] = _token_fingerprint(val) or ""
    except OSError:
        pass
    return tokens


def _scan_launch_agent(label: str) -> DuplicateService:
    """Inspect a macOS LaunchAgent plist by label."""
    import plistlib
    import subprocess

    plist_path = os.path.expanduser(f"~/Library/LaunchAgents/{label}.plist")
    service = DuplicateService(label=label, plist_path=plist_path)
    service.installed = os.path.exists(plist_path)

    if service.installed:
        try:
            with open(plist_path, "rb") as handle:
                data = plistlib.load(handle)
            env = data.get("EnvironmentVariables") or {}
            for key, val in env.items():
                if key.endswith("_TOKEN") and val:
                    fp = _token_fingerprint(str(val))
                    if fp:
                        service.token_fingerprints[key] = fp
        except Exception:
            pass

    try:
        result = subprocess.run(
            ["launchctl", "list", label],
            capture_output=True,
            text=True,
        )
        service.running = result.returncode == 0
        if service.running and result.stdout:
            parts = result.stdout.strip().split("\t")
            if len(parts) >= 1 and parts[0].isdigit():
                service.pid = int(parts[0])
    except Exception:
        pass

    return service


def _read_hermes_platform_state() -> Dict[str, Any]:
    """Read Hermes runtime platform state if present."""
    import json

    path = os.path.expanduser("~/.hermes/gateway_state.json")
    if not os.path.exists(path):
        return {}
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
        platforms = data.get("platforms") or {}
        return platforms if isinstance(platforms, dict) else {}
    except Exception:
        return {}


def check_duplicates(
    config_path: str,
) -> DuplicateCheckResult:
    """Scan for competing gateway services and shared Slack tokens."""
    warnings: List[str] = []
    services: List[DuplicateService] = []

    for label in ("ai.praison.bot", "ai.hermes.gateway"):
        services.append(_scan_launch_agent(label))

    praison_env = _read_env_file_tokens(os.path.expanduser("~/.praisonai/.env"))
    hermes_env = _read_env_file_tokens(os.path.expanduser("~/.hermes/.env"))

    fingerprint_map: Dict[str, List[str]] = {}
    for source, mapping in (("praisonai", praison_env), ("hermes", hermes_env)):
        for key, fp in mapping.items():
            fingerprint_map.setdefault(fp, []).append(f"{source}:{key}")

    for service in services:
        for key, fp in service.token_fingerprints.items():
            fingerprint_map.setdefault(fp, []).append(f"{service.label}:{key}")

    shared = [
        fp for fp, owners in fingerprint_map.items() if len(set(owners)) > 1
    ]

    hermes_platforms = _read_hermes_platform_state()
    if hermes_platforms.get("slack", {}).get("state") == "connected":
        warnings.append(
            "Hermes Slack is connected — events may split if SLACK_APP_TOKEN is shared."
        )
    if hermes_platforms.get("telegram", {}).get("state") == "connected":
        warnings.append(
            "Hermes Telegram is connected — stopping ai.hermes.gateway affects Telegram."
        )

    pid_lock: Optional[Dict[str, Any]] = None
    try:
        host, port = resolve_gateway_endpoint(config_path)
        from praisonai_bot.gateway.port_utils import GatewayPIDLock

        pid_lock = GatewayPIDLock(host=host, port=port).get_lock_info()
        if pid_lock and pid_lock.get("is_running"):
            daemon = _scan_launch_agent("ai.praison.bot")
            if daemon.pid and pid_lock.get("pid") and daemon.pid != pid_lock["pid"]:
                warnings.append(
                    f"LaunchAgent PID ({daemon.pid}) differs from gateway lock PID "
                    f"({pid_lock['pid']})."
                )
    except Exception:
        pass

    log_path = default_log_path()
    if os.path.exists(log_path):
        try:
            with open(log_path, encoding="utf-8", errors="replace") as handle:
                tail = handle.read()[-8000:]
            if "Conflict: terminated by other getUpdates request" in tail:
                warnings.append(
                    "Telegram getUpdates Conflict detected — another bot may be polling."
                )
        except OSError:
            pass

    ok = not shared and not any(
        s.label == "ai.hermes.gateway"
        and s.running
        and hermes_platforms.get("slack", {}).get("state") == "connected"
        for s in services
    )
    if shared:
        warnings.append(
            "Shared token fingerprint detected across services — inbound events may split."
        )

    return DuplicateCheckResult(
        ok=ok,
        services=services,
        shared_tokens=shared,
        hermes_platforms=hermes_platforms,
        pid_lock=pid_lock,
        warnings=warnings,
    )


def resolve_platform_dlq_path(platform: str) -> str:
    """Resolve the durable inbound DLQ path for a platform."""
    from praisonai_bot.bots._session import resolve_durable_store_dir

    store_dir = resolve_durable_store_dir(platform)
    return str(store_dir / "inbound_dlq.sqlite")


def _sessions_dir() -> str:
    from praisonaiagents.paths import get_sessions_dir

    return str(get_sessions_dir())


def list_gateway_sessions(
    platform: Optional[str] = None,
    active_seconds: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """List stored gateway bot session files."""
    import json
    import time

    sessions: List[Dict[str, Any]] = []
    base = _sessions_dir()
    if not os.path.isdir(base):
        return sessions

    prefix = f"bot_{platform}_" if platform else "bot_"
    for fname in sorted(os.listdir(base)):
        if not fname.endswith(".json") or not fname.startswith(prefix):
            continue
        path = os.path.join(base, fname)
        try:
            with open(path, encoding="utf-8") as handle:
                data = json.load(handle)
        except (OSError, json.JSONDecodeError):
            continue
        updated = data.get("updated_at") or data.get("created_at")
        if active_seconds and updated:
            try:
                if time.time() - float(updated) > active_seconds:
                    continue
            except (TypeError, ValueError):
                pass
        sessions.append(
            {
                "session_id": data.get("session_id") or fname[:-5],
                "platform": platform or fname.split("_")[1] if fname.count("_") >= 2 else "",
                "user_id": data.get("user_id"),
                "message_count": len(data.get("messages") or []),
                "updated_at": updated,
                "path": path,
            }
        )
    return sessions


def show_gateway_session(
    session_ref: str,
    tail: int = 20,
) -> Dict[str, Any]:
    """Show a stored session by id or user id suffix."""
    import json

    base = _sessions_dir()
    candidates = []
    if os.path.isfile(session_ref):
        candidates = [session_ref]
    elif os.path.isfile(os.path.join(base, f"{session_ref}.json")):
        candidates = [os.path.join(base, f"{session_ref}.json")]
    else:
        for fname in os.listdir(base) if os.path.isdir(base) else []:
            if session_ref in fname:
                candidates.append(os.path.join(base, fname))

    if not candidates:
        raise FileNotFoundError(f"Session not found: {session_ref}")

    path = sorted(candidates)[0]
    with open(path, encoding="utf-8") as handle:
        data = json.load(handle)

    messages = data.get("messages") or []
    return {
        "session_id": data.get("session_id"),
        "user_id": data.get("user_id"),
        "agent_name": data.get("agent_name"),
        "message_count": len(messages),
        "messages": messages[-tail:],
        "path": path,
        "footer": (
            "Sessions reflect stored history; use `praisonai gateway test "
            "--check-inbound` for live delivery."
        ),
    }
