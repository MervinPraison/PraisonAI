"""Map between agents-tier browser protocols and praisonai_browser runtime dicts."""

from __future__ import annotations

from typing import Any, Dict, Union

from praisonaiagents.tools.protocols.browser import (
    BrowserAction,
    BrowserActionType,
    BrowserObservation,
    BrowserSession,
)

# Agent/runtime actions that extend the base protocol enum (now in BrowserActionType).
_EXTRA_ACTIONS = frozenset()


def observation_from_dict(data: Dict[str, Any]) -> BrowserObservation:
    """Convert a runtime observation dict to agents-tier ``BrowserObservation``."""
    return BrowserObservation.from_dict(data)


def observation_to_dict(observation: Union[BrowserObservation, Dict[str, Any]]) -> Dict[str, Any]:
    if isinstance(observation, BrowserObservation):
        return observation.to_dict()
    return observation


def _action_type_from_name(name: str) -> Union[BrowserActionType, str]:
    try:
        return BrowserActionType(name)
    except ValueError:
        # Extra actions extend the base protocol enum; pass them through as
        # strings (BrowserActionType is a str subclass, so this stays compatible).
        if name in _EXTRA_ACTIONS:
            return name
        return BrowserActionType.WAIT


def action_from_agent_dict(data: Dict[str, Any]) -> BrowserAction:
    """Convert agent/runtime action dict to agents-tier ``BrowserAction``."""
    raw = data.get("action", "wait")
    action_type = _action_type_from_name(str(raw))
    text = data.get("text") or data.get("value")
    return BrowserAction(
        action=action_type,
        selector=data.get("selector"),
        text=text,
        url=data.get("url"),
        direction=data.get("direction"),
        thought=data.get("thought", ""),
        done=bool(data.get("done", False)),
        error=data.get("error"),
    )


def action_to_agent_dict(action: BrowserAction) -> Dict[str, Any]:
    """Convert agents-tier action to runtime dict (extension/CDP wire format)."""
    payload = action.to_dict()
    if action.text is not None:
        payload["value"] = action.text
    return payload


def session_from_dict(data: Dict[str, Any]) -> BrowserSession:
    return BrowserSession(
        session_id=data.get("session_id", data.get("id", "")),
        goal=data.get("goal", data.get("task", "")),
        status=data.get("status", "pending"),
        steps=data.get("steps", []),
        current_url=data.get("current_url", data.get("url")),
        started_at=data.get("started_at"),
        ended_at=data.get("ended_at"),
        error=data.get("error"),
    )
