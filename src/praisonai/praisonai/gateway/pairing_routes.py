"""
Starlette routes for pairing management API.

Provides REST endpoints for approving pairing requests:
- GET    /api/pairing/pending
- POST   /api/pairing/approve
- POST   /api/pairing/revoke
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List

from starlette.responses import JSONResponse

from .pairing import PairingStore

logger = logging.getLogger(__name__)


def create_pairing_routes(pairing_store: PairingStore, auth_checker: callable, rate_limiter: Any = None):
    """Create pairing management route handlers.
    
    Args:
        pairing_store: PairingStore instance
        auth_checker: Function that checks authentication and returns error response or None
        rate_limiter: Optional rate limiter instance
    
    Returns:
        Dictionary of route handlers
    """
    
    async def pending(request):
        """GET /api/pairing/pending — list pending pairing requests."""
        auth_err = auth_checker(request)
        if auth_err:
            return auth_err

        if rate_limiter:
            client_ip = request.client.host if request.client else "unknown"
            if not rate_limiter.allow("pairing_pending", client_ip):
                retry = rate_limiter.time_until_allowed("pairing_pending", client_ip)
                return JSONResponse(
                    {"error": "Rate limited", "retry_after_seconds": round(retry)},
                    status_code=429,
                )

        pending_list = pairing_store.list_pending()
        return JSONResponse({"pending": pending_list})

    async def approve(request):
        """POST /api/pairing/approve — approve a pairing request.
        
        Body: {"channel": "telegram", "code": "ABCD1234"}
        """
        auth_err = auth_checker(request)
        if auth_err:
            return auth_err

        if rate_limiter:
            client_ip = request.client.host if request.client else "unknown"
            if not rate_limiter.allow("pairing_approve", client_ip):
                retry = rate_limiter.time_until_allowed("pairing_approve", client_ip)
                return JSONResponse(
                    {"error": "Rate limited", "retry_after_seconds": round(retry)},
                    status_code=429,
                )

        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"error": "Invalid JSON"}, status_code=400)

        channel = body.get("channel", "")
        code = body.get("code", "")

        if not channel or not code:
            return JSONResponse(
                {"error": "Both 'channel' and 'code' are required"}, 
                status_code=400,
            )

        success = pairing_store.approve(channel, code)
        if not success:
            return JSONResponse(
                {"error": "Invalid or expired code"}, 
                status_code=404,
            )

        try:
            from praisonaiagents.bus import get_default_bus, Event
            get_default_bus().publish_event(Event(type="pairing_approved", data={"channel": channel, "code": code}))
        except Exception as _bus_exc:
            logger.debug("EventBus emit skipped: %s", _bus_exc)

        return JSONResponse({
            "approved": True,
            "channel": channel,
            "code": code,
        })

    async def revoke(request):
        """POST /api/pairing/revoke — revoke a paired channel.
        
        Body: {"channel": "telegram", "user_id": "12345"}
        """
        auth_err = auth_checker(request)
        if auth_err:
            return auth_err

        if rate_limiter:
            client_ip = request.client.host if request.client else "unknown"
            if not rate_limiter.allow("pairing_revoke", client_ip):
                retry = rate_limiter.time_until_allowed("pairing_revoke", client_ip)
                return JSONResponse(
                    {"error": "Rate limited", "retry_after_seconds": round(retry)},
                    status_code=429,
                )

        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"error": "Invalid JSON"}, status_code=400)

        channel = body.get("channel", "")
        user_id = body.get("user_id", "")

        if not channel or not user_id:
            return JSONResponse(
                {"error": "Both 'channel' and 'user_id' are required"}, 
                status_code=400,
            )

        success = pairing_store.revoke(user_id, channel)
        if not success:
            return JSONResponse(
                {"error": "Channel not found or not paired"}, 
                status_code=404,
            )

        return JSONResponse({
            "revoked": True,
            "channel": channel,
            "user_id": user_id,
        })

    return {
        "pending": pending,
        "approve": approve,  
        "revoke": revoke,
    }