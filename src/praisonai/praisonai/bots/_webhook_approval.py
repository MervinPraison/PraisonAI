"""
Webhook Approval Backend for PraisonAI Agents.

Implements the ApprovalProtocol by POSTing approval requests to an external
webhook URL and polling a status endpoint (or the same URL with GET) for the
decision.  Ideal for enterprise integrations, custom dashboards, and CI/CD
pipelines.

Usage::

    from praisonaiagents import Agent
    from praisonai.bots import WebhookApproval

    agent = Agent(
        name="assistant",
        tools=[execute_command],
        approval=WebhookApproval(
            webhook_url="https://my-app.com/api/approvals",
        ),
    )
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
import uuid
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class WebhookApproval:
    """Approval backend that sends HTTP webhook requests and polls for decisions.

    Posts a JSON payload to ``webhook_url`` with the approval request details,
    then polls ``status_url`` (defaults to ``webhook_url/{request_id}``) for
    the decision.

    Satisfies :class:`praisonaiagents.approval.protocols.ApprovalProtocol`.

    Args:
        webhook_url: URL to POST approval requests to.  Falls back to
            ``APPROVAL_WEBHOOK_URL`` env var.
        status_url: URL template to GET decision status.  Use ``{request_id}``
            placeholder.  Defaults to ``webhook_url/{request_id}``.
        headers: Extra HTTP headers (e.g. auth tokens).
        timeout: Max seconds to wait for a response (default 300).
        poll_interval: Seconds between status polls (default 5.0).

    Example::

        from praisonai.bots import WebhookApproval
        agent = Agent(
            name="bot",
            approval=WebhookApproval(
                webhook_url="https://hooks.example.com/approve",
                headers={"Authorization": "Bearer sk-xxx"},
            ),
        )
    """

    def __init__(
        self,
        webhook_url: Optional[str] = None,
        status_url: Optional[str] = None,
        headers: Optional[Dict[str, str]] = None,
        timeout: float = 300,
        poll_interval: float = 5.0,
    ):
        self._webhook_url = webhook_url or os.environ.get("APPROVAL_WEBHOOK_URL", "")
        if not self._webhook_url:
            raise ValueError(
                "Webhook URL is required. Pass webhook_url= or set APPROVAL_WEBHOOK_URL env var."
            )
        self._status_url = status_url
        self._headers = headers or {}
        self._timeout = timeout
        self._poll_interval = poll_interval

    def __repr__(self) -> str:
        return f"WebhookApproval(webhook_url={self._webhook_url!r})"

    # ── Internal HTTP helper ───────────────────────────────────────────

    async def _http_request(
        self,
        method: str,
        url: str,
        payload: Optional[Dict[str, Any]] = None,
        session: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """Make an HTTP request. Override in tests for mocking."""
        import aiohttp

        headers = {"Content-Type": "application/json"}
        headers.update(self._headers)

        async def _do(s):
            if method.upper() == "GET":
                async with s.get(
                    url, headers=headers,
                    timeout=aiohttp.ClientTimeout(total=15),
                ) as resp:
                    if resp.content_type == "application/json":
                        return await resp.json()
                    text = await resp.text()
                    return {"status": resp.status, "body": text}
            else:
                async with s.post(
                    url, headers=headers, json=payload or {},
                    timeout=aiohttp.ClientTimeout(total=15),
                ) as resp:
                    if resp.content_type == "application/json":
                        return await resp.json()
                    text = await resp.text()
                    return {"status": resp.status, "body": text}

        if session is not None:
            return await _do(session)
        else:
            async with aiohttp.ClientSession() as _session:
                return await _do(_session)

    # ── ApprovalProtocol implementation ─────────────────────────────────

    async def request_approval(self, request) -> Any:
        """POST approval request to webhook and poll for decision."""
        from praisonaiagents.approval.protocols import ApprovalDecision
        import aiohttp

        request_id = str(uuid.uuid4())

        payload = {
            "request_id": request_id,
            "tool_name": request.tool_name,
            "arguments": request.arguments,
            "risk_level": request.risk_level,
            "agent_name": request.agent_name,
            "session_id": request.session_id,
            "context": request.context,
        }

        async with aiohttp.ClientSession() as session:
            try:
                # 1. POST the approval request
                post_data = await self._http_request(
                    "POST", self._webhook_url, payload, session=session,
                )

                # Check for immediate decision
                if isinstance(post_data, dict):
                    if "approved" in post_data:
                        return ApprovalDecision(
                            approved=bool(post_data["approved"]),
                            reason=post_data.get("reason", "Webhook immediate response"),
                            approver=post_data.get("approver"),
                            metadata={"platform": "webhook", "request_id": request_id},
                        )

                # 2. Poll for decision
                status_url = self._status_url or f"{self._webhook_url}/{request_id}"
                if "{request_id}" in status_url:
                    status_url = status_url.replace("{request_id}", request_id)

                decision = await self._poll_for_decision(
                    status_url, request_id, session=session,
                )
                return decision

            except Exception as e:
                logger.error(f"WebhookApproval error: {e}")
                return ApprovalDecision(
                    approved=False,
                    reason=f"Webhook approval error: {e}",
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

    # ── Polling ─────────────────────────────────────────────────────────

    async def _poll_for_decision(
        self,
        status_url: str,
        request_id: str,
        session: Optional[Any] = None,
    ) -> Any:
        """Poll the status endpoint for a decision."""
        from praisonaiagents.approval.protocols import ApprovalDecision

        deadline = time.monotonic() + self._timeout

        while time.monotonic() < deadline:
            await asyncio.sleep(self._poll_interval)

            try:
                data = await self._http_request("GET", status_url, session=session)

                if not isinstance(data, dict):
                    continue

                # Check if decision is available (status may be int from HTTP status when response isn't JSON)
                status = data.get("status", "")
                status = str(status).lower() if status is not None else ""
                if status == "pending":
                    continue

                if "approved" in data:
                    return ApprovalDecision(
                        approved=bool(data["approved"]),
                        reason=data.get("reason", f"Webhook decision for {request_id}"),
                        approver=data.get("approver"),
                        metadata={"platform": "webhook", "request_id": request_id},
                    )

                if status in ("approved", "approve", "yes"):
                    return ApprovalDecision(
                        approved=True,
                        reason=data.get("reason", "Approved via webhook"),
                        approver=data.get("approver"),
                        metadata={"platform": "webhook", "request_id": request_id},
                    )
                if status in ("denied", "deny", "rejected", "no"):
                    return ApprovalDecision(
                        approved=False,
                        reason=data.get("reason", "Denied via webhook"),
                        approver=data.get("approver"),
                        metadata={"platform": "webhook", "request_id": request_id},
                    )

            except Exception as e:
                logger.warning(f"Webhook poll exception: {e}")

        return ApprovalDecision(
            approved=False,
            reason=f"Timed out waiting for webhook approval ({int(self._timeout)}s)",
            metadata={"platform": "webhook", "request_id": request_id, "timeout": True},
        )
