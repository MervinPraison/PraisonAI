"""Generic declarative webhook-trigger channel — any HTTP event → agent.

Turns an arbitrary third-party webhook (GitHub, Stripe, CI, alerting, an
internal service) into an agent trigger through configuration alone, with no
bespoke adapter code. It composes primitives the gateway already owns rather
than re-implementing them:

- HMAC verification via :class:`~praisonai_bot.bots.webhook_security.HmacWebhookVerifier`
  and the fail-closed :func:`enforce_webhook_verification` gate;
- declarative payload/header/query filtering via the core
  :class:`praisonaiagents.bots.WebhookFilter`;
- durable, de-duplicated inbound dispatch via ``BotSessionManager`` (the same
  ingress journal + reset policy every other channel uses).

Usage (Python)::

    from praisonai_bot.bots import WebhookBot, WebhookRoute
    from praisonai_bot.bots.webhook_security import HmacWebhookVerifier

    bot = WebhookBot(
        agent=triage,
        path="/hooks/github",
        verify=HmacWebhookVerifier(
            secret=GH_SECRET, signature_headers=["X-Hub-Signature-256"],
            prefix="sha256=",
        ),
        routes=[
            WebhookRoute(
                when={"all": [
                    {"field": "headers.X-GitHub-Event", "equals": "issues"},
                    {"field": "payload.action", "in": ["opened", "reopened"]},
                ]},
                prompt="New issue #{{ payload.issue.number }}: "
                       "{{ payload.issue.title }}",
            ),
        ],
    )
    await bot.start()

Usage (YAML gateway channel)::

    channels:
      github:
        type: webhook
        path: /hooks/github
        verify:
          hmac: { header: X-Hub-Signature-256, secret: ${GITHUB_WEBHOOK_SECRET} }
        routes:
          - when:
              all:
                - { field: headers.X-GitHub-Event, equals: issues }
                - { field: payload.action, in: [opened, reopened] }
            agent: triage
            prompt: "New issue #{{ payload.issue.number }}: {{ payload.issue.title }}"
          - when: { field: payload.action, equals: closed }
            silent: true
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from praisonaiagents import Agent

from praisonaiagents.bots import (
    BotConfig,
    PlatformCapabilities,
    WebhookFilter,
    resolve_field,
)

logger = logging.getLogger(__name__)

# Matches ``{{ payload.issue.title }}`` style placeholders in a prompt template.
_TEMPLATE_RE = re.compile(r"\{\{\s*([^}]+?)\s*\}\}")


@dataclass
class WebhookRoute:
    """A single declarative route for a :class:`WebhookBot`.

    Attributes:
        when: A declarative filter tree (see :class:`praisonaiagents.bots.
            WebhookFilter`). ``None``/empty matches every event (catch-all).
        agent: Optional agent id/name — informational for gateway routing
            (the adapter runs its bound ``agent``). Kept so YAML routes can name
            a target agent per the config surface.
        prompt: A template string for the agent prompt. ``{{ dotted.path }}``
            placeholders are filled from the normalised event. When omitted, the
            raw JSON payload is used as the prompt.
        silent: When True, a matching event is acknowledged (HTTP 200) but no
            agent runs — drops noisy events at the edge.
    """

    when: Optional[Any] = None
    agent: Optional[str] = None
    prompt: Optional[str] = None
    silent: bool = False
    _filter: WebhookFilter = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._filter = WebhookFilter(self.when)

    def matches(self, event: Mapping[str, Any]) -> bool:
        """Return whether ``event`` satisfies this route's filter."""
        return self._filter.matches(event)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "WebhookRoute":
        """Build a route from a parsed YAML mapping."""
        return cls(
            when=data.get("when"),
            agent=data.get("agent"),
            prompt=data.get("prompt"),
            silent=bool(data.get("silent", False)),
        )


def render_prompt(
    template: Optional[str],
    event: Mapping[str, Any],
    *,
    route_name: str = "",
) -> str:
    """Render a ``{{ dotted.path }}`` prompt template against an event.

    Missing paths render as an empty string (fail-safe). When ``template`` is
    None, the raw JSON payload is used so a route with no ``prompt`` still yields
    a usable agent input.

    Externally-POSTed payload content reaches the agent as untrusted data, so
    the payload-derived portion is delimiter-fenced (via
    :func:`praisonaiagents.tools.trust.wrap_request_payload`) — the model is
    instructed to treat it as data, not instructions. For a route with no
    ``prompt``, a fixed operator line is prefixed *outside* the fence so the
    model never sees attacker-controlled text as its sole instruction.
    """
    from praisonaiagents.tools.trust import (
        request_payload_notice,
        wrap_request_payload,
    )

    notice = request_payload_notice()

    if template is None:
        payload = event.get("payload")
        try:
            rendered = json.dumps(payload, ensure_ascii=False, default=str)
        except (TypeError, ValueError):
            rendered = str(payload)
        where = f" on route {route_name}" if route_name else ""
        prefix = (
            f"An external event was received{where}; the payload follows. "
            f"{notice}"
        )
        return f"{prefix}\n\n{wrap_request_payload(rendered)}"

    fenced = False

    def _sub(match: "re.Match[str]") -> str:
        nonlocal fenced
        value = resolve_field(event, match.group(1).strip())
        if value is None:
            return ""
        fenced = True
        return wrap_request_payload(str(value))

    rendered = _TEMPLATE_RE.sub(_sub, template)
    # Prepend the inline untrusted-data notice once (outside the fence) so the
    # semantics travel with the payload even when the agent runs with
    # ``use_system_prompt=False`` and never sees the system-prompt trust clause.
    return f"{notice}\n\n{rendered}" if fenced else rendered


def _build_verifier_from_config(verify: Any) -> Optional[Any]:
    """Build a verifier from a declarative ``verify`` mapping, if given.

    Supports the ``{"hmac": {"header": ..., "secret": ..., "prefix": ...}}``
    shape used in YAML. An already-constructed verifier object (anything
    exposing ``verify``) is returned unchanged. Returns None when no verifier is
    configured.
    """
    if verify is None:
        return None
    if hasattr(verify, "verify"):
        return verify
    if isinstance(verify, Mapping):
        hmac_cfg = verify.get("hmac") if "hmac" in verify else verify
        if isinstance(hmac_cfg, Mapping):
            secret = hmac_cfg.get("secret", "")
            header = hmac_cfg.get("header") or hmac_cfg.get("signature_header")
            headers = hmac_cfg.get("signature_headers") or (
                [header] if header else ["X-Signature"]
            )
            from praisonai_bot.bots.webhook_security import HmacWebhookVerifier

            return HmacWebhookVerifier(
                secret=secret,
                signature_headers=headers,
                digest=hmac_cfg.get("digest", "sha256"),
                prefix=hmac_cfg.get("prefix"),
            )
    return None


class WebhookBot:
    """First-class generic webhook ingress channel for the gateway.

    Serves an HTTP endpoint, verifies the request (fail-closed), evaluates a
    declarative route filter tree, and dispatches matching events to the bound
    agent through the durable ``BotSessionManager`` — reusing the gateway's
    existing reliability seams instead of living outside it.
    """

    _outbound_platform = "webhook"
    # A webhook ingress owns its own HTTP server lifecycle; the single-Bot
    # supervisor keeps it alive via the running-flag poll rather than a
    # reconnect loop.
    supervised_inbound = True

    def __init__(
        self,
        token: str = "",
        agent: Optional["Agent"] = None,
        config: Optional[BotConfig] = None,
        *,
        path: str = "/webhook",
        webhook_port: int = 8080,
        verify: Any = None,
        routes: Optional[List[Any]] = None,
        **kwargs: Any,
    ) -> None:
        self._extra_kwargs = kwargs
        self._agent = agent
        self.config = config or BotConfig(token=token, mode="webhook")
        self._path = path if path.startswith("/") else f"/{path}"
        self._webhook_port = int(webhook_port)
        self._verifier = _build_verifier_from_config(verify)

        self._routes: List[WebhookRoute] = []
        for r in routes or []:
            if isinstance(r, WebhookRoute):
                self._routes.append(r)
            elif isinstance(r, Mapping):
                self._routes.append(WebhookRoute.from_dict(r))
        # No routes declared → an unconditional catch-all so a bare
        # ``type: webhook`` channel still triggers the agent on every event.
        if not self._routes:
            self._routes.append(WebhookRoute())

        self._is_running = False
        self._started_at: Optional[float] = None
        self._runner: Any = None
        self._site: Any = None

        from ._session import build_session_manager

        self._session_mgr = build_session_manager(self.config, platform="webhook")

    # ── Capabilities / descriptor ───────────────────────────────────

    @classmethod
    def default_capabilities(cls) -> PlatformCapabilities:
        return PlatformCapabilities(
            accepts_webhooks=True,
            verifies_webhook_signature=True,
        )

    # ── Properties ──────────────────────────────────────────────────

    @property
    def is_running(self) -> bool:
        return self._is_running

    @property
    def platform(self) -> str:
        return "webhook"

    @property
    def webhook_verifier(self) -> Optional[Any]:
        return self._verifier

    # ── Lifecycle ───────────────────────────────────────────────────

    async def start(self) -> None:
        """Start the webhook HTTP server."""
        if self._is_running:
            return

        try:
            from aiohttp import web
        except ImportError:  # pragma: no cover - optional dep
            raise ImportError("aiohttp required: pip install aiohttp")

        app = web.Application()
        app.router.add_post(self._path, self._handle_webhook)
        app.router.add_get(self._path, self._handle_health)

        self._runner = web.AppRunner(app)
        await self._runner.setup()
        self._site = web.TCPSite(self._runner, "0.0.0.0", self._webhook_port)
        await self._site.start()

        self._is_running = True
        self._started_at = time.time()
        logger.info(
            "Webhook channel listening on http://0.0.0.0:%s%s",
            self._webhook_port,
            self._path,
        )

    async def stop(self) -> None:
        """Stop the webhook HTTP server."""
        if not self._is_running:
            return
        if self._site:
            await self._site.stop()
        if self._runner:
            await self._runner.cleanup()
        self._is_running = False
        self._started_at = None
        logger.info("Webhook channel stopped")

    # ── HTTP handlers ───────────────────────────────────────────────

    async def _handle_health(self, request: Any) -> Any:
        from aiohttp import web

        return web.Response(status=200, text="Webhook endpoint")

    async def _handle_webhook(self, request: Any) -> Any:
        from aiohttp import web
        from praisonai_bot.bots.webhook_security import (
            enforce_webhook_verification,
        )

        try:
            raw_body = await request.read()
        except Exception:  # noqa: BLE001
            return web.Response(status=400, text="Bad request")

        headers = dict(request.headers)
        if not enforce_webhook_verification(
            accepts_webhooks=True,
            verifier=self._verifier,
            headers=headers,
            raw_body=raw_body,
            platform="webhook",
        ):
            return web.Response(status=401, text="Invalid signature")

        try:
            payload = json.loads(raw_body.decode("utf-8")) if raw_body else {}
        except (json.JSONDecodeError, UnicodeDecodeError):
            payload = {"_raw": raw_body.decode("utf-8", "replace")}

        event = {
            "payload": payload,
            "headers": headers,
            "query": dict(request.query),
        }

        route = self._match_route(event)
        if route is None:
            # No route matched — acknowledge and drop (nothing to trigger).
            return web.Response(status=200, text="No matching route")
        if route.silent:
            return web.Response(status=200, text="OK")

        try:
            await self._dispatch(route, event, raw_body)
        except Exception:  # noqa: BLE001
            # Fail loud on dispatch: surface a 5xx so the sender retries the
            # delivery instead of a false 200 ack that silently drops the event.
            logger.error("Webhook agent dispatch failed", exc_info=True)
            return web.Response(status=500, text="Dispatch failed")
        return web.Response(status=200, text="OK")

    def _match_route(self, event: Mapping[str, Any]) -> Optional[WebhookRoute]:
        """Return the first route whose filter matches, or None."""
        for route in self._routes:
            try:
                if route.matches(event):
                    return route
            except Exception:  # noqa: BLE001 - a bad filter never crashes ingress
                logger.debug("Webhook route filter raised; skipping", exc_info=True)
        return None

    async def _dispatch(
        self, route: WebhookRoute, event: Mapping[str, Any], raw_body: bytes
    ) -> None:
        """Render the prompt and run the agent through the session manager.

        Raises on dispatch failure so the HTTP handler can return a 5xx and the
        sender retries, rather than silently acknowledging a dropped event.
        """
        if not self._agent:
            logger.warning("Webhook channel has no agent configured")
            return

        prompt = render_prompt(route.prompt, event, route_name=self._path)
        message_id = self._message_id_for(event, raw_body)
        user_id = f"webhook:{self._path}"
        await self._session_mgr.chat(
            self._agent,
            user_id,
            prompt,
            message_id=message_id,
        )

    def _message_id_for(
        self, event: Mapping[str, Any], raw_body: bytes
    ) -> str:
        """Return a stable dedup/ingress-journal id for this delivery.

        Prefers a provider-supplied delivery id header (GitHub/Stripe/generic),
        and otherwise falls back to a deterministic hash of the channel path +
        raw request body. The fallback keeps ingress journaling and
        deduplication active for generic senders that omit a delivery header —
        without it an empty ``message_id`` silently disables both.
        """
        headers = event.get("headers", {})
        lowered = {str(k).lower(): v for k, v in headers.items()}
        delivery_id = (
            lowered.get("x-github-delivery")
            or lowered.get("x-request-id")
            or lowered.get("x-delivery-id")
            or lowered.get("stripe-signature")
        )
        if delivery_id:
            return str(delivery_id)
        digest = hashlib.sha256(self._path.encode("utf-8") + b"\x00" + raw_body)
        return f"webhook-{digest.hexdigest()}"

    # ── Agent integration ───────────────────────────────────────────

    def set_agent(self, agent: "Agent") -> None:
        self._agent = agent

    def get_agent(self) -> Optional["Agent"]:
        return self._agent
