"""
Inbound trigger (webhook) contract for the PraisonAI gateway.

This module is **protocol-only** and carries no heavy dependencies. It defines
the declarative shape of an inbound event trigger — an authenticated HTTP
surface that, on receiving an external payload, runs an agent (or wakes a
session) and delivers the result through a channel.

The HTTP route registration, request authentication, idempotency store, rate
limiting and channel delivery all live in the ``praisonai`` wrapper gateway
(``praisonai.gateway.server``). Here we only describe:

- ``HookConfig``: the declarative trigger definition (path/auth/action/agent/
  session/idempotency/delivery/message).
- ``render_template``: a tiny, dependency-free ``{{ payload.x }}`` / ``{x}``
  templating helper used to build session keys, idempotency keys and messages
  from a JSON payload.
- ``compute_idempotency_key``: derive a stable dedup key from a payload.
- ``InboundTriggerProtocol``: the structural contract a gateway implements to
  register hooks.

It sits alongside the existing internal lifecycle hooks (``SCHEDULE_TRIGGER``,
``GATEWAY_START``) as the *inbound* counterpart: those fire from inside the
process; this fires from an external HTTP request.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Protocol, runtime_checkable

__all__ = [
    "HookAction",
    "HookConfig",
    "render_template",
    "compute_idempotency_key",
    "InboundTriggerProtocol",
]


class HookAction:
    """Allowed hook actions (string constants, kept dependency-free)."""

    AGENT = "agent"  # Run an agent turn on the templated message.
    WAKE = "wake"  # Nudge an existing session without a new user message.

    @classmethod
    def all(cls) -> "list[str]":
        return [cls.AGENT, cls.WAKE]


# Matches both ``{{ payload.a.b }}`` (Jinja-ish) and ``{a.b}`` (str.format-ish)
# placeholders so the same template works across the YAML and Python surfaces.
_DOUBLE_BRACE = re.compile(r"\{\{\s*([^}]+?)\s*\}\}")
_SINGLE_BRACE = re.compile(r"\{\s*([^{}]+?)\s*\}")


def _lookup(path: str, payload: Dict[str, Any]) -> Any:
    """Resolve a dotted ``path`` against ``payload``.

    A leading ``payload.`` prefix is optional, so ``{{ payload.from }}`` and
    ``{from}`` resolve identically. Missing keys resolve to an empty string so
    a template never raises on a partial payload.
    """
    key = path.strip()
    if key.startswith("payload."):
        key = key[len("payload."):]
    elif key == "payload":
        return payload

    current: Any = payload
    for part in key.split("."):
        part = part.strip()
        if not part:
            continue
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return ""
    return current


def render_template(template: Optional[str], payload: Dict[str, Any]) -> str:
    """Render ``template`` against ``payload`` with no external dependencies.

    Supports ``{{ payload.x }}`` and ``{x}`` placeholders resolving dotted
    paths into the JSON ``payload``. Returns an empty string when ``template``
    is falsy. Unknown placeholders render as empty strings rather than raising.

    Args:
        template: The template string (or None).
        payload: The decoded JSON request body.

    Returns:
        The rendered string.
    """
    if not template:
        return ""

    def _double(match: "re.Match[str]") -> str:
        value = _lookup(match.group(1), payload)
        return "" if value is None else str(value)

    def _single(match: "re.Match[str]") -> str:
        value = _lookup(match.group(1), payload)
        return "" if value is None else str(value)

    rendered = _DOUBLE_BRACE.sub(_double, template)
    rendered = _SINGLE_BRACE.sub(_single, rendered)
    return rendered


def compute_idempotency_key(
    template: Optional[str],
    payload: Dict[str, Any],
    *,
    path: str = "",
) -> str:
    """Derive a stable idempotency key for a hook delivery.

    When ``template`` is provided it is rendered against ``payload`` and the
    result (scoped by ``path``) is hashed. When it is not, the whole payload is
    hashed deterministically so identical retried deliveries still dedup.

    Args:
        template: Optional idempotency-key template (e.g. ``"{message_id}"``).
        payload: The decoded JSON request body.
        path: The hook path, mixed in so the same id on different hooks does
            not collide.

    Returns:
        A hex digest usable as a dedup key.
    """
    if template:
        rendered = render_template(template, payload).strip()
        if rendered:
            basis = f"{path}\x00{rendered}"
            return hashlib.sha256(basis.encode("utf-8")).hexdigest()

    # Fall back to a deterministic hash of the full payload.
    import json

    try:
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    except (TypeError, ValueError):
        canonical = repr(payload)
    basis = f"{path}\x00{canonical}"
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()


@dataclass
class HookConfig:
    """Declarative definition of an inbound event trigger.

    Exposes ``POST /hooks/<path>`` on the gateway. On a request the gateway
    authenticates, deduplicates, resolves a session, runs the agent (or wakes a
    session), and delivers the reply through the delivery router.

    Attributes:
        path: URL path segment, e.g. ``"gmail"`` exposes ``POST /hooks/gmail``.
        agent: Agent id to run (``action="agent"``). Defaults to the gateway's
            first registered agent when omitted.
        action: ``"agent"`` runs a turn, ``"wake"`` nudges a session.
        auth: Optional bearer token / shared secret required on the request.
            When omitted the gateway's own ``auth_token`` is used.
        session_key: Template for the session id, so related events share
            context, e.g. ``"hook:gmail:{message_id}"``.
        idempotency_key: Template for the dedup key, e.g. ``"{message_id}"``.
            When omitted the whole payload is hashed.
        deliver_to: ``channel:target`` delivery spec for the agent reply, e.g.
            ``"telegram:123456789"``. Omit to skip outbound delivery.
        message: Template for the message built from the payload.
        enabled: Whether the hook is active.
        metadata: Free-form extra settings.
    """

    path: str
    agent: Optional[str] = None
    action: str = HookAction.AGENT
    auth: Optional[str] = None
    session_key: Optional[str] = None
    idempotency_key: Optional[str] = None
    deliver_to: Optional[str] = None
    message: Optional[str] = None
    enabled: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.path = (self.path or "").strip().strip("/")
        if not self.path:
            raise ValueError("HookConfig.path must be a non-empty path segment")
        if self.action not in HookAction.all():
            raise ValueError(
                f"HookConfig.action must be one of {HookAction.all()}, "
                f"got {self.action!r}"
            )

    @property
    def route(self) -> str:
        """The full gateway route this hook is served on."""
        return f"/hooks/{self.path}"

    def resolve_session_key(self, payload: Dict[str, Any]) -> str:
        """Resolve the session id for ``payload``.

        Falls back to a stable per-hook key when no ``session_key`` template is
        configured, so a hook without an explicit key still groups its events.
        """
        if self.session_key:
            rendered = render_template(self.session_key, payload).strip()
            if rendered:
                return rendered
        return f"hook:{self.path}"

    def resolve_idempotency_key(self, payload: Dict[str, Any]) -> str:
        """Resolve the dedup key for ``payload``."""
        return compute_idempotency_key(
            self.idempotency_key, payload, path=self.path
        )

    def resolve_message(self, payload: Dict[str, Any]) -> str:
        """Render the agent message for ``payload``."""
        return render_template(self.message, payload)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to a dictionary (hides the auth secret)."""
        return {
            "path": self.path,
            "agent": self.agent,
            "action": self.action,
            "auth": "***" if self.auth else None,
            "session_key": self.session_key,
            "idempotency_key": self.idempotency_key,
            "deliver_to": self.deliver_to,
            "message": self.message,
            "enabled": self.enabled,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "HookConfig":
        """Create a ``HookConfig`` from a parsed YAML/JSON mapping."""
        known = {
            "path",
            "agent",
            "action",
            "auth",
            "session_key",
            "idempotency_key",
            "deliver_to",
            "message",
            "enabled",
            "metadata",
        }
        return cls(
            path=data.get("path", ""),
            agent=data.get("agent"),
            action=data.get("action", HookAction.AGENT),
            auth=data.get("auth"),
            session_key=data.get("session_key"),
            idempotency_key=data.get("idempotency_key"),
            deliver_to=data.get("deliver_to"),
            message=data.get("message"),
            enabled=data.get("enabled", True),
            metadata={
                **(data.get("metadata") or {}),
                **{k: v for k, v in data.items() if k not in known},
            },
        )


@runtime_checkable
class InboundTriggerProtocol(Protocol):
    """Structural contract a gateway implements to host inbound triggers."""

    def register_hook(self, hook: "HookConfig | Dict[str, Any]", **kwargs: Any) -> str:
        """Register an inbound trigger, returning its path."""
        ...

    def unregister_hook(self, path: str) -> bool:
        """Remove a registered hook by path."""
        ...

    def list_hooks(self) -> "list[str]":
        """List registered hook paths."""
        ...
