"""Optional L3 page — bot / channel health.

Renders the attached gateway's ``health()`` (status, uptime, per-channel bot
state) and its agents as aiui components: status chips, metrics and tables,
with explicit empty and error states.
"""

from __future__ import annotations

import inspect
from typing import Any, Dict, List, Optional, Sequence, Tuple

import praisonaiui as aiui
from praisonaiui import ui

from ._blocks import clip, count, duration, timestamp

# gateway health()["status"] -> (chip label, badge variant)
_GATEWAY_STATUS = {
    "healthy": ("Healthy", "default"),
    "running": ("Running", "default"),
    "ok": ("Healthy", "default"),
    "stopped": ("Stopped", "secondary"),
    "degraded": ("Degraded", "destructive"),
    "unhealthy": ("Unhealthy", "destructive"),
}


def gateway_chip(status: Any) -> Tuple[str, str]:
    """Chip label and variant for a gateway status (no status: attached in-process)."""
    if status is None or status == "":
        return ("Attached", "secondary")
    return _GATEWAY_STATUS.get(str(status).lower(), ("Unknown", "outline"))


def channel_state(entry: Dict[str, Any]) -> Tuple[str, str]:
    """Chip label and variant for one ``health()["channels"]`` entry."""
    if str(entry.get("status", "")).lower() == "degraded":
        return ("Degraded", "destructive")
    if entry.get("ok"):
        return ("Healthy", "default")
    if entry.get("running"):
        return ("Running", "secondary")
    return ("Stopped", "outline")


def build_bot_health(
    health: Optional[Dict[str, Any]],
    *,
    agents: Sequence[Tuple[str, Optional[str]]] = (),
    channels_feature: Optional[Dict[str, Any]] = None,
    error: Optional[str] = None,
) -> Dict[str, Any]:
    """The page as an ``aiui.layout``.

    ``health`` is the gateway's ``health()`` dict, or None when no gateway is
    attached. ``agents`` are ``(id, name)`` pairs. ``channels_feature`` is
    aiui's channels feature health (channels configured on the Channels page).
    """
    if error is not None:
        return ui.layout([
            ui.alert("The gateway did not return its health status.", variant="error",
                     title="Bot health unavailable"),
            ui.caption(clip(error, 300)),
        ])
    if health is None:
        return ui.layout([
            ui.alert("No gateway is attached to this UI, so there is no bot status to show.",
                     variant="warning", title="Gateway not connected"),
            ui.empty("Start the UI with a gateway (praisonai serve gateway, or pass gateway= to "
                     "configure_host) to see channel health here."),
        ])

    label, variant = gateway_chip(health.get("status"))
    raw_channels = health.get("channels")
    channels = raw_channels if isinstance(raw_channels, dict) else {}
    states = [channel_state(e if isinstance(e, dict) else {}) for e in channels.values()]
    healthy = sum(1 for s, _ in states if s == "Healthy")

    stats = [
        {"label": "Uptime", "value": duration(health.get("uptime"))},
        {"label": "Agents", "value": count(health.get("agents", len(agents)))},
        {"label": "Sessions", "value": count(health.get("sessions"))},
        {"label": "Channels healthy", "value": f"{healthy} / {len(channels)}"},
    ]
    if channels_feature:
        stats.append({
            "label": "Channels page running",
            "value": f"{count(channels_feature.get('running_channels'))} / "
                     f"{count(channels_feature.get('total_channels'))}",
        })

    blocks: List[Dict[str, Any]] = [
        ui.badge(f"Gateway: {label}", variant=variant),
        ui.stat_group(stats),
        ui.header("Channels", level=3),
    ]
    if channels:
        rows = []
        for (name, entry), (state, _) in zip(channels.items(), states):
            entry = entry if isinstance(entry, dict) else {}
            rows.append([
                clip(name, 60),
                clip(entry.get("platform"), 40),
                state,
                clip(entry.get("reason")),
                timestamp(entry.get("last_activity")),
            ])
        blocks.append(ui.table(headers=["Channel", "Platform", "State", "Reason", "Last activity"],
                               rows=rows))
    else:
        blocks.append(ui.empty("No channel bots are running on this gateway. "
                               "Add one on the Channels page."))

    blocks.append(ui.header("Agents", level=3))
    if agents:
        blocks.append(ui.table(headers=["Agent ID", "Name"],
                               rows=[[clip(aid, 60), clip(name, 60)] for aid, name in agents]))
    else:
        blocks.append(ui.empty("No agents are registered with the gateway."))
    return ui.layout(blocks)


async def collect_bot_health() -> Dict[str, Any]:
    """Read the live gateway and channels feature, then build the page."""
    try:
        from praisonaiui.features._gateway_ref import get_gateway
    except ImportError:
        return build_bot_health(None)

    channels_feature = None
    try:
        from praisonaiui.features import get_feature

        feat = get_feature("channels")
        if feat is not None:
            channels_feature = await feat.health()
    except Exception:  # noqa: BLE001 - the extra counts are optional
        channels_feature = None

    gw = get_gateway()
    if gw is None:
        return build_bot_health(None)
    try:
        health: Any = gw.health() if callable(getattr(gw, "health", None)) else {}
        if inspect.isawaitable(health):
            health = await health
        if not isinstance(health, dict):
            health = {}
        agents: List[Tuple[str, Optional[str]]] = []
        if callable(getattr(gw, "list_agents", None)):
            for aid in list(gw.list_agents()):
                agent = gw.get_agent(aid) if callable(getattr(gw, "get_agent", None)) else None
                agents.append((str(aid), getattr(agent, "name", None)))
    except Exception as exc:  # noqa: BLE001 - shown as the page's error state
        return build_bot_health(None, error=f"{type(exc).__name__}: {exc}")
    return build_bot_health(health, agents=agents, channels_feature=channels_feature)


@aiui.page("bot-health", title="Bot Health", icon="🤖")
async def bot_health_page():
    """Dashboard page for channel and gateway status."""
    return await collect_bot_health()
