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
            return name, await asyncio.wait_for(bot.probe(), timeout=timeout)
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
