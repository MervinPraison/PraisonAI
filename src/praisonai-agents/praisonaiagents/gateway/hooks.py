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
- ``CoalesceConfig``: opt-in burst coalescing — deliveries sharing a
  payload-derived group key within a debounce window collapse into one run.
- ``InboundTriggerProtocol``: the structural contract a gateway implements to
  register hooks.

It sits alongside the existing internal lifecycle hooks (``SCHEDULE_TRIGGER``,
``GATEWAY_START``) as the *inbound* counterpart: those fire from inside the
process; this fires from an external HTTP request.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import math
import re
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable

__all__ = [
    "CoalesceConfig",
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


def render_template(
    template: Optional[str],
    payload: Dict[str, Any],
    *,
    fence_values: bool = False,
) -> str:
    """Render ``template`` against ``payload`` with no external dependencies.

    Supports ``{{ payload.x }}`` and ``{x}`` placeholders resolving dotted
    paths into the JSON ``payload``. Returns an empty string when ``template``
    is falsy. Unknown placeholders render as empty strings rather than raising.

    Args:
        template: The template string (or None).
        payload: The decoded JSON request body.
        fence_values: When True, each interpolated payload-derived value is
            wrapped in an ``<external_request_payload>`` fence so the agent
            treats it as untrusted data, not instructions. The operator's own
            static template text stays outside the fence. Used for the agent
            message (see :meth:`HookConfig.resolve_message`); left False for
            session/idempotency keys where fencing would corrupt the value.

    Returns:
        The rendered string.
    """
    if not template:
        return ""

    wrap = None
    notice = None
    if fence_values:
        from praisonaiagents.tools.trust import (
            request_payload_notice as notice,
            wrap_request_payload as wrap,
        )

    fenced = False

    def _resolve(match: "re.Match[str]") -> str:
        nonlocal fenced
        # group(1) is the ``{{ ... }}`` body, group(2) the ``{ ... }`` body.
        expr = match.group(1) if match.group(1) is not None else match.group(2)
        value = _lookup(expr, payload)
        if value is None:
            return ""
        if wrap is None:
            return str(value)
        fenced = True
        return wrap(str(value))

    rendered = _PLACEHOLDER.sub(_resolve, template)
    # Prepend the inline untrusted-data notice once (outside the fence) when a
    # payload value was fenced, so the semantics travel with the message even if
    # the agent runs with ``use_system_prompt=False``.
    if fenced and notice is not None:
        return f"{notice()}\n\n{rendered}"
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


SIGNATURE_SCHEMES = ("hmac_hex", "hmac_base64", "hmac_timestamped", "structured")


def _parse_structured(value: str) -> "tuple[Optional[str], List[str]]":
    """Split a composite ``t=…,v1=…`` header into (timestamp, [v1 signatures])."""
    timestamp: Optional[str] = None
    signatures: List[str] = []
    for part in value.split(","):
        key, sep, val = part.strip().partition("=")
        if not sep:
            continue
        if key == "t":
            timestamp = val
        elif key == "v1":
            signatures.append(val)
    return timestamp, signatures


def _timestamp_fresh(timestamp: Optional[str], tolerance_seconds: float) -> bool:
    """Whether a unix ``timestamp`` (seconds) is within ``tolerance_seconds`` of now."""
    try:
        ts = float(str(timestamp).strip())
    except (TypeError, ValueError):
        return False
    return abs(time.time() - ts) <= tolerance_seconds


def verify_webhook_signature(
    secret: Optional[str],
    raw_body: bytes,
    signature: Optional[str],
    *,
    algo: str = "sha256",
    prefix: Optional[str] = None,
    scheme: str = "hmac_hex",
    timestamp: Optional[str] = None,
    tolerance_seconds: float = 0,
) -> bool:
    """Constant-time HMAC verification of a webhook body (dependency-free).

    A pure counterpart to ``compute_idempotency_key`` that lets the core
    contract validate a provider signature over the *raw* request bytes without
    importing the wrapper's crypto. Mirrors the wrapper's ``verify_hmac``: it is
    fail-closed (a missing secret/signature or unknown ``algo``/``scheme``
    returns ``False`` rather than raising) and prefix-aware.

    Args:
        secret: Shared signing secret. Falsy → ``False``.
        raw_body: The exact raw request body bytes the provider signed.
        signature: The signature header value the provider sent.
        algo: Hash algorithm name (e.g. ``"sha256"``, ``"sha1"``).
        prefix: Optional signature prefix (e.g. ``"sha256="``). When provided,
            the comparison is against the fully-prefixed computed value, so the
            caller passes the raw header value unchanged. When omitted, an
            ``algo=`` style prefix on the provided signature is auto-stripped.
        scheme: ``"hmac_hex"`` (default, hex HMAC of the body),
            ``"hmac_base64"`` (base64 HMAC of the body), ``"hmac_timestamped"``
            (hex HMAC of ``"{timestamp}.{body}"``) or ``"structured"`` (a
            ``t=…,v1=…`` header; hex HMAC of ``"{t}.{body}"``, any ``v1`` may
            match).
        timestamp: Provider timestamp (unix seconds). For ``"structured"`` it
            is read from the ``t=`` component when not given.
        tolerance_seconds: When > 0, a missing or stale timestamp (outside
            ``±tolerance_seconds`` of now) is rejected — the replay window.

    Returns:
        ``True`` only if a non-empty signature matches the computed HMAC using a
        constant-time comparison (and, when enforced, the timestamp is fresh).
    """
    if not secret or not signature or scheme not in SIGNATURE_SCHEMES:
        return False

    candidates = [signature]
    if scheme == "structured":
        parsed_ts, candidates = _parse_structured(signature)
        timestamp = timestamp or parsed_ts
        if not candidates:
            return False

    if tolerance_seconds and tolerance_seconds > 0:
        if not _timestamp_fresh(timestamp, tolerance_seconds):
            return False

    secret_bytes = secret.encode("utf-8") if isinstance(secret, str) else secret
    body_bytes = raw_body if isinstance(raw_body, bytes) else str(raw_body).encode("utf-8")
    if scheme in ("hmac_timestamped", "structured"):
        if not timestamp:
            return False
        body_bytes = f"{timestamp}.".encode("utf-8") + body_bytes

    try:
        digest = hmac.new(secret_bytes, body_bytes, algo).digest()
    except (ValueError, TypeError):
        return False
    if scheme == "hmac_base64":
        computed = base64.b64encode(digest).decode("ascii")
    else:
        computed = digest.hex()

    if prefix:
        computed = f"{prefix}{computed}"
    matched = False
    for provided in candidates:
        if not prefix and scheme != "hmac_base64" and "=" in provided \
                and provided.split("=", 1)[0].isalnum():
            provided = provided.split("=", 1)[1]
        # Evaluate every candidate so timing does not reveal which one matched.
        matched |= hmac.compare_digest(computed, provided)
    return matched


@dataclass
class CoalesceConfig:
    """Opt-in burst coalescing for a hook (Issue #5867).

    Deliveries whose ``group_key`` renders to the same value are collapsed into
    one run carrying the latest payload. The run fires once the group has been
    quiet for ``window_seconds``, or at the latest ``max_wait_seconds`` after
    its first delivery so a steady stream cannot starve dispatch. The buffering
    and timer live in the gateway runtime; this is only the contract.

    Attributes:
        group_key: Template over the payload, e.g.
            ``"{repository.full_name}#{pull_request.number}"``. A delivery whose
            key renders empty is dispatched immediately (never coalesced).
        window_seconds: Debounce quiet window.
        max_wait_seconds: Hard cap from the first delivery in a group.
    """

    group_key: str
    window_seconds: float = 30.0
    max_wait_seconds: float = 300.0

    def __post_init__(self) -> None:
        if not (self.group_key or "").strip():
            raise ValueError("CoalesceConfig.group_key must be a non-empty template")
        self.window_seconds = float(self.window_seconds)
        self.max_wait_seconds = float(self.max_wait_seconds)
        if not (
            math.isfinite(self.window_seconds) and math.isfinite(self.max_wait_seconds)
        ):
            raise ValueError("CoalesceConfig durations must be finite")
        if self.window_seconds <= 0:
            raise ValueError("CoalesceConfig.window_seconds must be > 0")
        if self.max_wait_seconds < self.window_seconds:
            raise ValueError(
                "CoalesceConfig.max_wait_seconds must be >= window_seconds"
            )

    def deadline(self, first_at: float, last_at: float) -> float:
        """When a group first seen at ``first_at`` and last at ``last_at`` fires."""
        return min(last_at + self.window_seconds, first_at + self.max_wait_seconds)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "group_key": self.group_key,
            "window_seconds": self.window_seconds,
            "max_wait_seconds": self.max_wait_seconds,
        }


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
            When omitted the gateway's own ``auth_token`` is used, unless
            ``secret`` is set with a timestamped scheme (``hmac_timestamped``
            or ``structured``) and ``signature_tolerance_seconds > 0``: that
            replay-bounded signature then authenticates on its own. A
            body-only HMAC (``hmac_hex``/``hmac_base64``) still needs the
            gateway token, since a captured delivery could be replayed.
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
        signature_scheme: ``"hmac_hex"`` (default), ``"hmac_base64"``,
            ``"hmac_timestamped"`` (signs ``"{timestamp}.{body}"``) or
            ``"structured"`` (a ``t=…,v1=…`` header, Stripe-style).
        timestamp_header: Header carrying the provider timestamp (unix
            seconds); only valid with a scheme that signs it. For
            ``"structured"`` the ``t=`` component is used.
        signature_tolerance_seconds: Replay window for the timestamped and
            structured schemes: a request outside ``±`` this many seconds is
            rejected before any agent runs. ``0`` disables the freshness
            check; negative values are rejected.
        events: Optional allow-list of event types. A delivery whose event is
            not listed is acknowledged (200) without running a turn.
        event_header: Header carrying the event type, e.g. ``"X-GitHub-Event"``.
            When omitted the event is read from the payload (dotted path) via
            ``resolve_event``.
        deliver_only: When ``True`` the rendered ``message`` *is* the delivered
            content, routed straight through ``deliver_to`` with no LLM turn.
        coalesce: Optional :class:`CoalesceConfig` (or mapping) that collapses
            a burst of deliveries for the same entity into one run. ``None``
            (default) runs once per delivery.
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
    signature_scheme: str = "hmac_hex"
    timestamp_header: Optional[str] = None
    signature_tolerance_seconds: int = 300
    # Event filtering.
    events: Optional[List[str]] = None
    event_header: Optional[str] = None
    # Pass-through: deliver the rendered message with no LLM turn.
    deliver_only: bool = False
    # Burst coalescing (#5867).
    coalesce: Optional[CoalesceConfig] = None

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
        if isinstance(self.coalesce, dict):
            self.coalesce = CoalesceConfig(**self.coalesce)
        if self.signature_scheme not in SIGNATURE_SCHEMES:
            raise ValueError(
                f"HookConfig.signature_scheme must be one of "
                f"{list(SIGNATURE_SCHEMES)}, got {self.signature_scheme!r}"
            )
        # A body-only scheme does not sign the timestamp, so an attacker could
        # replay an old body+signature with a fresh header: refuse rather than
        # offer a replay window that does not hold.
        if self.timestamp_header and self.signature_scheme not in (
            "hmac_timestamped", "structured",
        ):
            raise ValueError(
                "HookConfig.timestamp_header requires signature_scheme "
                "'hmac_timestamped' or 'structured' (the timestamp must be signed)"
            )
        # ``structured`` carries ``t=`` in the signature header itself, but
        # ``hmac_timestamped`` has nowhere to read it from without a header and
        # would silently reject every request.
        if self.signature_scheme == "hmac_timestamped" and not self.timestamp_header:
            raise ValueError(
                "HookConfig.signature_scheme 'hmac_timestamped' requires timestamp_header"
            )
        try:
            self.signature_tolerance_seconds = int(self.signature_tolerance_seconds)
        except (TypeError, ValueError):
            raise ValueError(
                "HookConfig.signature_tolerance_seconds must be an integer, "
                f"got {self.signature_tolerance_seconds!r}"
            ) from None
        if self.signature_tolerance_seconds < 0:
            raise ValueError(
                "HookConfig.signature_tolerance_seconds must be >= 0 (0 disables)"
            )
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
        lowered = {k.lower(): v for k, v in headers.items()}
        signature = None
        if self.signature_header:
            signature = lowered.get(self.signature_header.lower())
        timestamp = None
        if self.timestamp_header:
            timestamp = lowered.get(self.timestamp_header.lower())
            if self.signature_scheme == "structured" and timestamp:
                # Same composite header (``t=…,v1=…``): take the ``t=`` part.
                timestamp = _parse_structured(timestamp)[0] or timestamp
        # Freshness only applies when the timestamp is signed, so a plain
        # body-only hook is unaffected.
        timestamped = self.signature_scheme in ("hmac_timestamped", "structured")
        return verify_webhook_signature(
            self.secret,
            raw_body,
            signature,
            algo=self.signature_algo,
            prefix=self.signature_prefix,
            scheme=self.signature_scheme,
            timestamp=timestamp,
            tolerance_seconds=self.signature_tolerance_seconds if timestamped else 0,
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

    def resolve_coalesce_key(self, payload: Dict[str, Any]) -> Optional[str]:
        """Resolve the coalescing group for ``payload``.

        Returns ``None`` when coalescing is not configured or the group key
        renders empty, meaning the delivery runs on its own immediately.
        """
        if self.coalesce is None:
            return None
        rendered = render_template(self.coalesce.group_key, payload).strip()
        return f"{self.path}\x00{rendered}" if rendered else None

    def resolve_message(self, payload: Dict[str, Any], *, fence: bool = True) -> str:
        """Render the hook message for ``payload``.

        Payload-derived interpolations are fenced as untrusted request data so
        the agent never treats externally-POSTed content as instructions; the
        operator's own template text stays outside the fence.

        Args:
            payload: The decoded request body.
            fence: When True (the agent-turn default), interpolated payload
                values are wrapped in an ``<external_request_payload>`` fence.
                Pass ``fence=False`` for ``deliver_only`` hooks, where the
                rendered message is delivered verbatim to a channel with no
                agent consuming (and therefore stripping) the fence markup.
        """
        return render_template(self.message, payload, fence_values=fence)

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
            "signature_scheme": self.signature_scheme,
            "timestamp_header": self.timestamp_header,
            "signature_tolerance_seconds": self.signature_tolerance_seconds,
            "events": list(self.events) if self.events else None,
            "event_header": self.event_header,
            "deliver_only": self.deliver_only,
            "coalesce": self.coalesce.to_dict() if self.coalesce else None,
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
            "signature_scheme",
            "timestamp_header",
            "signature_tolerance_seconds",
            "events",
            "event_header",
            "deliver_only",
            "coalesce",
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
            signature_scheme=data.get("signature_scheme", "hmac_hex"),
            timestamp_header=data.get("timestamp_header"),
            signature_tolerance_seconds=data.get("signature_tolerance_seconds", 300),
            events=data.get("events"),
            event_header=data.get("event_header"),
            deliver_only=data.get("deliver_only", False),
            coalesce=data.get("coalesce"),
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
