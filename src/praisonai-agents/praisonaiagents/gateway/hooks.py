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
import hmac
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable

__all__ = [
    "HookAction",
    "HookConfig",
    "InboundTriggerProtocol",
    "compute_idempotency_key",
    "render_template",
    "verify_webhook_signature",
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
# A single combined pattern is used (double-brace alternative first so it wins)
# so each placeholder is substituted exactly once in one pass — a payload value
# that itself contains ``{...}`` is therefore never re-expanded.
_PLACEHOLDER = re.compile(r"\{\{\s*([^}]+?)\s*\}\}|\{\s*([^{}]+?)\s*\}")


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

    def _resolve(match: "re.Match[str]") -> str:
        # group(1) is the ``{{ ... }}`` body, group(2) the ``{ ... }`` body.
        expr = match.group(1) if match.group(1) is not None else match.group(2)
        value = _lookup(expr, payload)
        return "" if value is None else str(value)

    return _PLACEHOLDER.sub(_resolve, template)


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


def verify_webhook_signature(
    secret: Optional[str],
    raw_body: bytes,
    signature: Optional[str],
    *,
    algo: str = "sha256",
    prefix: Optional[str] = None,
) -> bool:
    """Constant-time HMAC verification of a webhook body (dependency-free).

    A pure counterpart to ``compute_idempotency_key`` that lets the core
    contract validate a provider signature over the *raw* request bytes without
    importing the wrapper's crypto. Mirrors the wrapper's ``verify_hmac``: it is
    fail-closed (a missing secret/signature or unknown ``algo`` returns
    ``False`` rather than raising) and prefix-aware.

    Args:
        secret: Shared signing secret. Falsy → ``False``.
        raw_body: The exact raw request body bytes the provider signed.
        signature: The signature header value the provider sent.
        algo: Hash algorithm name (e.g. ``"sha256"``, ``"sha1"``).
        prefix: Optional signature prefix (e.g. ``"sha256="``). When provided,
            the comparison is against the fully-prefixed computed value, so the
            caller passes the raw header value unchanged. When omitted, an
            ``algo=`` style prefix on the provided signature is auto-stripped.

    Returns:
        ``True`` only if a non-empty signature matches the computed HMAC using a
        constant-time comparison.
    """
    if not secret or not signature:
        return False

    secret_bytes = secret.encode("utf-8") if isinstance(secret, str) else secret
    body_bytes = raw_body if isinstance(raw_body, bytes) else str(raw_body).encode("utf-8")

    try:
        computed = hmac.new(secret_bytes, body_bytes, algo).hexdigest()
    except (ValueError, TypeError):
        return False

    provided = signature
    if prefix:
        return hmac.compare_digest(f"{prefix}{computed}", provided)

    if "=" in provided and provided.split("=", 1)[0].isalnum():
        provided = provided.split("=", 1)[1]
    return hmac.compare_digest(computed, provided)


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
        secret: Optional HMAC signing secret. When set, the gateway verifies the
            provider signature over the *raw* body before any agent runs and
            rejects (401) a missing/invalid signature — fail-closed.
        signature_header: Header carrying the signature, e.g.
            ``"X-Hub-Signature-256"``.
        signature_algo: Digest for the HMAC, e.g. ``"sha256"``.
        signature_prefix: Optional signature prefix, e.g. ``"sha256="``.
        events: Optional allow-list of event types. A delivery whose event is
            not listed is acknowledged (200) without running a turn.
        event_header: Header carrying the event type, e.g. ``"X-GitHub-Event"``.
            When omitted the event is read from the payload (dotted path) via
            ``resolve_event``.
        deliver_only: When ``True`` the rendered ``message`` *is* the delivered
            content, routed straight through ``deliver_to`` with no LLM turn.
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
    # Signature verification (over the RAW body, before the agent runs).
    secret: Optional[str] = None
    signature_header: Optional[str] = None
    signature_algo: str = "sha256"
    signature_prefix: Optional[str] = None
    # Event filtering.
    events: Optional[List[str]] = None
    event_header: Optional[str] = None
    # Pass-through: deliver the rendered message with no LLM turn.
    deliver_only: bool = False

    def __post_init__(self) -> None:
        self.path = (self.path or "").strip().strip("/")
        if not self.path:
            raise ValueError("HookConfig.path must be a non-empty path segment")
        if self.action not in HookAction.all():
            raise ValueError(
                f"HookConfig.action must be one of {HookAction.all()}, "
                f"got {self.action!r}"
            )
        if isinstance(self.events, str):
            self.events = [self.events]
        # A configured secret with no explicit header would otherwise read no
        # signature and reject every request. Default to the widely-used
        # ``X-Hub-Signature-256`` (GitHub/webhook convention) so ``secret`` on
        # its own is a working, verifying configuration rather than a 401 trap.
        if self.secret and not self.signature_header:
            self.signature_header = "X-Hub-Signature-256"

    def verify_signature(
        self, raw_body: bytes, headers: Dict[str, str]
    ) -> bool:
        """Verify the provider HMAC signature over ``raw_body``.

        Returns ``True`` when no ``secret`` is configured (signature checking is
        opt-in); otherwise delegates to :func:`verify_webhook_signature`, which
        is fail-closed on a missing/invalid signature.
        """
        if not self.secret:
            return True
        signature = None
        if self.signature_header:
            lowered = {k.lower(): v for k, v in headers.items()}
            signature = lowered.get(self.signature_header.lower())
        return verify_webhook_signature(
            self.secret,
            raw_body,
            signature,
            algo=self.signature_algo,
            prefix=self.signature_prefix,
        )

    def resolve_event(
        self, payload: Dict[str, Any], headers: Optional[Dict[str, str]] = None
    ) -> str:
        """Resolve the event type from a header or the payload.

        Reads ``event_header`` from ``headers`` when configured, else treats
        ``event_header`` as a dotted payload path (defaulting to ``"event"``).
        Returns the base event name only (e.g. GitHub's ``"issues"``); a
        payload ``action`` sub-type (``"issues.opened"``) is matched separately
        by :meth:`event_allowed` so both ``issues`` and ``issues.opened`` work.
        """
        if self.event_header and headers:
            lowered = {k.lower(): v for k, v in headers.items()}
            value = lowered.get(self.event_header.lower())
            if value:
                return str(value)
        path = self.event_header or "event"
        value = _lookup(path, payload)
        return "" if value is None else str(value)

    def event_allowed(
        self, payload: Dict[str, Any], headers: Optional[Dict[str, str]] = None
    ) -> bool:
        """Whether the delivery's event passes the configured ``events`` filter.

        Returns ``True`` when no filter is set. The resolved base event (e.g.
        GitHub's ``"issues"``) matches a listed name that is equal to it or is
        namespaced under it (``"issues.opened"``); in the namespaced case the
        payload's ``action`` (when present) must equal the sub-type, so
        ``events: [issues.opened]`` accepts an ``issues`` delivery only when
        ``action == "opened"``.
        """
        if not self.events:
            return True
        event = self.resolve_event(payload, headers)
        if not event:
            return False
        action = payload.get("action") if isinstance(payload, dict) else None
        for allowed in self.events:
            if event == allowed:
                return True
            base, sep, sub = allowed.partition(".")
            # Namespaced sub-type (e.g. ``issues.opened``): fail-closed — the
            # payload must actually carry the matching ``action``. A delivery
            # that omits ``action`` is NOT admitted, so an ``issues`` event
            # cannot slip through a filter that only allows ``issues.opened``.
            if sep and base == event and action is not None and str(action) == sub:
                return True
        return False

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
        """Convert to a dictionary (hides the auth/signing secrets)."""
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
            "secret": "***" if self.secret else None,
            "signature_header": self.signature_header,
            "signature_algo": self.signature_algo,
            "signature_prefix": self.signature_prefix,
            "events": list(self.events) if self.events else None,
            "event_header": self.event_header,
            "deliver_only": self.deliver_only,
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
            "secret",
            "signature_header",
            "signature_algo",
            "signature_prefix",
            "events",
            "event_header",
            "deliver_only",
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
            secret=data.get("secret"),
            signature_header=data.get("signature_header"),
            signature_algo=data.get("signature_algo", "sha256"),
            signature_prefix=data.get("signature_prefix"),
            events=data.get("events"),
            event_header=data.get("event_header"),
            deliver_only=data.get("deliver_only", False),
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
