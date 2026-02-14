"""
HTTP Approval Backend for PraisonAI Agents.

Implements the ApprovalProtocol by starting a lightweight local HTTP server
that serves a minimal approval dashboard.  Approvers visit the URL in a
browser and click Approve / Deny.

Uses aiohttp.web — no extra dependencies beyond what PraisonAI already ships.

Usage::

    from praisonaiagents import Agent
    from praisonai.bots import HTTPApproval

    agent = Agent(
        name="assistant",
        tools=[execute_command],
        approval=HTTPApproval(host="0.0.0.0", port=8899),
    )
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class HTTPApproval:
    """Approval backend that serves a local HTTP dashboard for approvals.

    Starts an ephemeral aiohttp web server when the first approval is
    requested.  Each approval gets a unique URL.  The approver opens the
    URL in a browser and clicks Approve or Deny.

    Satisfies :class:`praisonaiagents.approval.protocols.ApprovalProtocol`.

    Args:
        host: Bind address (default ``127.0.0.1``).
        port: Port to listen on (default ``8899``).
        timeout: Max seconds to wait for a response (default 300).

    Example::

        from praisonai.bots import HTTPApproval
        agent = Agent(name="bot", approval=HTTPApproval(port=8899))
    """

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 8899,
        timeout: float = 300,
    ):
        self._host = host
        self._port = port
        self._timeout = timeout
        self._pending: Dict[str, Optional[Dict[str, Any]]] = {}
        self._server_started = False
        self._runner: Optional[Any] = None
        self._site: Optional[Any] = None

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

    async def _handle_page(self, request) -> Any:
        """Serve the approval page HTML."""
        from aiohttp import web

        request_id = request.match_info["request_id"]
        pending = self._pending.get(request_id)

        if pending is None:
            return web.Response(text="Approval request not found or already decided.", status=404)

        if pending.get("decided"):
            return web.Response(text="This approval has already been decided.", status=200)

        info = pending.get("info", {})
        html = self._build_html(request_id, info)
        return web.Response(text=html, content_type="text/html")

    async def _handle_decide(self, request) -> Any:
        """Handle approve/deny POST."""
        from aiohttp import web

        request_id = request.match_info["request_id"]
        pending = self._pending.get(request_id)

        if pending is None:
            return web.Response(text="Not found", status=404)
        if pending.get("decided"):
            return web.Response(text="Already decided", status=200)

        try:
            body = await request.json()
        except Exception:
            body = {}

        decision = body.get("decision", "deny")
        pending["decided"] = True
        pending["approved"] = decision == "approve"
        pending["reason"] = body.get("reason", f"{'Approved' if pending['approved'] else 'Denied'} via HTTP dashboard")
        pending["approver"] = body.get("approver", "http_user")

        return web.json_response({"ok": True, "decision": decision})

    def _build_html(self, request_id: str, info: Dict[str, Any]) -> str:
        """Build a minimal approval page."""
        tool_name = info.get("tool_name", "unknown")
        risk_level = info.get("risk_level", "unknown")
        agent_name = info.get("agent_name", "")
        arguments = info.get("arguments", {})

        args_html = ""
        for k, v in arguments.items():
            val_str = str(v)
            if len(val_str) > 200:
                val_str = val_str[:197] + "..."
            args_html += f"<tr><td><code>{k}</code></td><td><code>{val_str}</code></td></tr>"

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
  const res = await fetch('/approve/{request_id}/decide', {{
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

        await self._ensure_server()

        request_id = str(uuid.uuid4())
        self._pending[request_id] = {
            "decided": False,
            "approved": False,
            "info": {
                "tool_name": request.tool_name,
                "arguments": request.arguments,
                "risk_level": request.risk_level,
                "agent_name": request.agent_name,
            },
        }

        url = f"http://{self._host}:{self._port}/approve/{request_id}"
        logger.info(f"HTTPApproval: Waiting for decision at {url}")

        # Poll for decision
        deadline = time.monotonic() + self._timeout
        while time.monotonic() < deadline:
            await asyncio.sleep(0.5)

            pending = self._pending.get(request_id, {})
            if pending.get("decided"):
                # Cleanup
                del self._pending[request_id]
                return ApprovalDecision(
                    approved=pending["approved"],
                    reason=pending.get("reason", ""),
                    approver=pending.get("approver"),
                    metadata={"platform": "http", "request_id": request_id, "url": url},
                )

        # Timeout — cleanup
        self._pending.pop(request_id, None)
        return ApprovalDecision(
            approved=False,
            reason=f"Timed out waiting for HTTP approval ({int(self._timeout)}s)",
            metadata={"platform": "http", "request_id": request_id, "timeout": True},
        )

    def request_approval_sync(self, request) -> Any:
        """Synchronous wrapper — runs async method in a new event loop."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(asyncio.run, self.request_approval(request))
                return future.result(timeout=self._timeout + 10)
        else:
            return asyncio.run(self.request_approval(request))

    async def shutdown(self) -> None:
        """Stop the HTTP server gracefully."""
        if self._runner:
            await self._runner.cleanup()
            self._server_started = False
            logger.info("HTTPApproval server stopped")
