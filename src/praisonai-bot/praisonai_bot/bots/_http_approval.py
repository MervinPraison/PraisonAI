"""
HTTP Approval Backend for PraisonAI Agents.

Implements the ApprovalProtocol by starting a lightweight local HTTP server
that serves a minimal approval dashboard.  Approvers visit the URL in a
browser and click Approve / Deny.

Uses aiohttp.web — no extra dependencies beyond what PraisonAI already ships.

Usage::

    from praisonaiagents import Agent
    from praisonai_bot.bots import HTTPApproval

    agent = Agent(
        name="assistant",
        tools=[execute_command],
        approval=HTTPApproval(host="127.0.0.1", port=8899),
    )
"""

from __future__ import annotations

import asyncio
import logging
import os
import secrets
import time
import uuid
from typing import Any, Dict, Iterable, Optional

from ._approval_base import (
    DEFAULT_APPROVAL_TIMEOUT,
    DurableApprovalMixin,
    is_authorized_actor,
    normalize_approvers,
)

logger = logging.getLogger(__name__)


class HTTPApproval(DurableApprovalMixin):
    """Approval backend that serves a local HTTP dashboard for approvals.

    Starts an ephemeral aiohttp web server when the first approval is
    requested.  Each approval gets a unique URL.  The approver opens the
    URL in a browser and clicks Approve or Deny.

    Satisfies :class:`praisonaiagents.approval.protocols.ApprovalProtocol`.

    Args:
        host: Bind address (default ``127.0.0.1``).
        port: Port to listen on (default ``8899``).
        timeout: Max seconds to wait for a response (default 300).
        allowed_approvers: Optional allowlist of approver IDs permitted to
            resolve an approval. When provided, each pending approval mints a
            single-use token that is carried only in the per-approval URL; the
            resolver must present that token (and, when the request supplies an
            ``approver``, be in the allowlist) or the decision is rejected. When
            ``None`` (default) any visitor may decide (legacy behaviour,
            backward compatible). Falls back to a comma-separated
            ``HTTP_APPROVERS`` env var when not passed.

    Example::

        from praisonai_bot.bots import HTTPApproval
        agent = Agent(name="bot", approval=HTTPApproval(port=8899))
    """

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 8899,
        timeout: float = DEFAULT_APPROVAL_TIMEOUT,
        allowed_approvers: Optional[Iterable[str]] = None,
        store: Optional[Any] = None,
    ):
        self._host = host
        self._port = port
        self._timeout = timeout
        if allowed_approvers is None:
            _env = os.environ.get("HTTP_APPROVERS", "").strip()
            if _env:
                allowed_approvers = [a.strip() for a in _env.split(",") if a.strip()]
        self._allowed_approvers = normalize_approvers(allowed_approvers)
        self._pending: Dict[str, Optional[Dict[str, Any]]] = {}
        self._server_started = False
        self._runner: Optional[Any] = None
        self._site: Optional[Any] = None
        self._init_store(store)

    def __repr__(self) -> str:
        return f"HTTPApproval(host={self._host!r}, port={self._port})"

    # ── Web server ──────────────────────────────────────────────────────

    async def _ensure_server(self) -> None:
        """Start the aiohttp web server if not already running."""
        if self._server_started:
            return

        from aiohttp import web

        app = web.Application()
        app.router.add_get("/approve/{request_id}", self._handle_page)
        app.router.add_post("/approve/{request_id}/decide", self._handle_decide)

        self._runner = web.AppRunner(app)
        await self._runner.setup()
        self._site = web.TCPSite(self._runner, self._host, self._port)
        await self._site.start()
        self._server_started = True
        logger.info(f"HTTPApproval server started on http://{self._host}:{self._port}")

    def _token_ok(self, pending: Dict[str, Any], request) -> bool:
        """Return whether *request* carries the per-approval token.

        The token is minted per pending approval and embedded only in the URL
        handed to the authorised approver. A constant-time comparison is used so
        the endpoint does not leak the token via timing. When no allowlist is
        configured there is no token, so this is a no-op (legacy behaviour).
        """
        expected = pending.get("token")
        if not expected:
            return True
        supplied = request.query.get("token") or request.headers.get("X-Approval-Token", "")
        return secrets.compare_digest(str(supplied), str(expected))

    async def _handle_page(self, request) -> Any:
        """Serve the approval page HTML."""
        from aiohttp import web

        request_id = request.match_info["request_id"]
        pending = self._pending.get(request_id)

        if pending is None:
            return web.Response(text="Approval request not found or already decided.", status=404)

        if not self._token_ok(pending, request):
            logger.warning(
                "Unauthorised HTTP approval page access for %s", request_id,
            )
            return web.Response(text="Not authorized to view this approval.", status=403)

        if pending.get("decided"):
            return web.Response(text="This approval has already been decided.", status=200)

        info = pending.get("info", {})
        token = pending.get("token")
        html = self._build_html(request_id, info, token=token)
        return web.Response(text=html, content_type="text/html")

    async def _handle_decide(self, request) -> Any:
        """Handle approve/deny POST."""
        from aiohttp import web

        request_id = request.match_info["request_id"]
        pending = self._pending.get(request_id)

        if pending is None:
            return web.Response(text="Not found", status=404)

        if not self._token_ok(pending, request):
            logger.warning(
                "Unauthorised HTTP approval decision attempt for %s", request_id,
            )
            return web.json_response({"ok": False, "error": "unauthorized"}, status=403)

        if pending.get("decided"):
            return web.Response(text="Already decided", status=200)

        try:
            body = await request.json()
        except Exception:
            body = {}

        approver = body.get("approver", "http_user")

        # Authorisation boundary: when an allowlist is configured a free-text
        # ``approver`` must be one of the authorised approvers. The per-approval
        # token already proves the resolver received the private URL; the
        # allowlist additionally pins the recorded approver identity.
        if not is_authorized_actor(approver, self._allowed_approvers):
            logger.warning(
                "Unauthorised HTTP approver %r for %s", approver, request_id,
            )
            return web.json_response({"ok": False, "error": "unauthorized"}, status=403)

        decision = body.get("decision", "deny")
        pending["decided"] = True
        pending["approved"] = decision == "approve"
        pending["reason"] = body.get("reason", f"{'Approved' if pending['approved'] else 'Denied'} via HTTP dashboard")
        pending["approver"] = approver

        return web.json_response({"ok": True, "decision": decision})

    def _build_html(self, request_id: str, info: Dict[str, Any], token: Optional[str] = None) -> str:
        """Build a minimal approval page."""
        import html as html_module

        token_qs = f"?token={html_module.escape(str(token))}" if token else ""

        tool_name = html_module.escape(str(info.get("tool_name", "unknown")))
        risk_level = html_module.escape(str(info.get("risk_level", "unknown")))
        agent_name = html_module.escape(str(info.get("agent_name", "")))
        arguments = info.get("arguments", {})

        args_html = ""
        for k, v in arguments.items():
            val_str = html_module.escape(str(v))
            if len(val_str) > 200:
                val_str = val_str[:197] + "..."
            key_str = html_module.escape(str(k))
            args_html += f"<tr><td><code>{key_str}</code></td><td><code>{val_str}</code></td></tr>"

        risk_colors = {
            "critical": "#FF0000", "high": "#FF8C00",
            "medium": "#FFD700", "low": "#00CC00",
        }
        risk_color = risk_colors.get(risk_level, "#888")

        return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Tool Approval Required</title>
<style>
body {{ font-family: -apple-system, BlinkMacSystemFont, sans-serif; max-width: 600px; margin: 40px auto; padding: 20px; background: #1a1a2e; color: #eee; }}
h1 {{ color: #fff; }} table {{ width: 100%; border-collapse: collapse; margin: 16px 0; }}
td {{ padding: 8px; border-bottom: 1px solid #333; }} code {{ background: #2a2a4a; padding: 2px 6px; border-radius: 3px; }}
.risk {{ display: inline-block; padding: 4px 12px; border-radius: 4px; font-weight: bold; color: #fff; background: {risk_color}; }}
.buttons {{ display: flex; gap: 12px; margin-top: 24px; }}
.btn {{ padding: 12px 32px; border: none; border-radius: 6px; font-size: 16px; cursor: pointer; font-weight: bold; }}
.approve {{ background: #00CC00; color: #000; }} .deny {{ background: #FF4444; color: #fff; }}
.done {{ text-align: center; margin-top: 24px; font-size: 18px; }}
</style></head><body>
<h1>🔒 Tool Approval Required</h1>
<p><strong>Tool:</strong> <code>{tool_name}</code></p>
<p><strong>Risk:</strong> <span class="risk">{risk_level.upper()}</span></p>
{"<p><strong>Agent:</strong> " + agent_name + "</p>" if agent_name else ""}
<h3>Arguments</h3>
<table>{args_html if args_html else "<tr><td><em>none</em></td></tr>"}</table>
<div class="buttons">
  <button class="btn approve" onclick="decide('approve')">✅ Approve</button>
  <button class="btn deny" onclick="decide('deny')">❌ Deny</button>
</div>
<div class="done" id="result" style="display:none"></div>
<script>
async function decide(d) {{
  const res = await fetch('/approve/{request_id}/decide{token_qs}', {{
    method: 'POST', headers: {{'Content-Type': 'application/json'}},
    body: JSON.stringify({{decision: d}})
  }});
  document.querySelector('.buttons').style.display = 'none';
  document.getElementById('result').style.display = 'block';
  document.getElementById('result').textContent = d === 'approve' ? '✅ Approved' : '❌ Denied';
}}
</script></body></html>"""

    # ── ApprovalProtocol implementation ─────────────────────────────────

    async def request_approval(self, request) -> Any:
        """Start server, register request, poll for decision."""
        from praisonaiagents.approval.protocols import ApprovalDecision

        await self._persist_pending(request, self._timeout)

        await self._ensure_server()

        request_id = str(uuid.uuid4())
        # Mint a single-use token bound to this approval when an allowlist is
        # configured, so only the holder of the private URL can resolve it.
        token = secrets.token_urlsafe(32) if self._allowed_approvers is not None else None
        self._pending[request_id] = {
            "decided": False,
            "approved": False,
            "token": token,
            "info": {
                "tool_name": request.tool_name,
                "arguments": request.arguments,
                "risk_level": request.risk_level,
                "agent_name": request.agent_name,
            },
        }

        url = f"http://{self._host}:{self._port}/approve/{request_id}"
        if token:
            url = f"{url}?token={token}"
        logger.info(f"HTTPApproval: Waiting for decision at {url}")
        print(f"\n🔗 Open this URL to approve/deny:\n   {url}\n")

        # Poll for decision
        deadline = time.monotonic() + self._timeout
        while time.monotonic() < deadline:
            await asyncio.sleep(0.5)

            pending = self._pending.get(request_id, {})
            if pending.get("decided"):
                # Cleanup
                del self._pending[request_id]
                decision = ApprovalDecision(
                    approved=pending["approved"],
                    reason=pending.get("reason", ""),
                    approver=pending.get("approver"),
                    metadata={"platform": "http", "request_id": request_id, "url": url},
                )
                await self._resolve_pending(request, decision)
                return decision

        # Timeout — cleanup
        self._pending.pop(request_id, None)
        decision = ApprovalDecision(
            approved=False,
            reason=f"Timed out waiting for HTTP approval ({int(self._timeout)}s)",
            metadata={"platform": "http", "request_id": request_id, "timeout": True},
        )
        await self._resolve_pending(request, decision)
        return decision

    def request_approval_sync(self, request) -> Any:
        """Synchronous wrapper — delegates to the shared async bridge."""
        from .._async_bridge import run_sync
        # run_sync raises RuntimeError if called from a running loop, so callers
        # in async contexts get a clear error instead of a silent thread cold-start.
        return run_sync(
            self.request_approval(request),
            timeout=self._timeout + 10,
        )

    async def shutdown(self) -> None:
        """Stop the HTTP server gracefully."""
        if self._runner:
            await self._runner.cleanup()
            self._server_started = False
            logger.info("HTTPApproval server stopped")
