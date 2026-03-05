"""Nightmarket API marketplace tools for AI agents.

Usage:
from praisonaiagents.tools import nightmarket_search, nightmarket_service_details, nightmarket_call

# Search for APIs
results = nightmarket_search("weather")

# Get service details
details = nightmarket_service_details("abc123")

# Call a service (returns 402 info for payment)
response = nightmarket_call("abc123", method="GET", params={"city": "NYC"})

Nightmarket (https://nightmarket.ai) is an API marketplace where AI agents discover
and pay for third-party services. Every call settles on-chain in USDC on Base using
the x402 payment protocol — no API keys or subscriptions needed.
"""

from typing import List, Dict, Optional
import logging
import json
from urllib.request import urlopen, Request
from urllib.error import HTTPError
from urllib.parse import urlencode, quote

logger = logging.getLogger(__name__)

NIGHTMARKET_BASE_URL = "https://nightmarket.ai/api"

# Allowed headers that can be passed through to API calls
_SAFE_HEADERS = frozenset({
    "accept", "content-type", "payment-signature", "authorization",
    "x-api-key", "user-agent",
})


def _validate_endpoint_id(endpoint_id: str) -> str:
    """Validate and sanitize endpoint_id to prevent path traversal."""
    sanitized = quote(endpoint_id, safe="")
    if ".." in endpoint_id or "/" in endpoint_id:
        raise ValueError(f"Invalid endpoint_id: {endpoint_id}")
    return sanitized


def nightmarket_search(query: str = "", sort: str = "popular") -> List[Dict]:
    """Search the Nightmarket API marketplace for available services.

    Args:
        query: Search term to filter by name, description, or seller (optional)
        sort: Sort order — 'popular', 'newest', 'price_asc', 'price_desc' (default: 'popular')

    Returns:
        List of available API services with id, name, description, method, price, and seller info
    """
    try:
        params = {"sort": sort}
        if query:
            params["search"] = query

        url = f"{NIGHTMARKET_BASE_URL}/marketplace?{urlencode(params)}"
        req = Request(url, headers={"Accept": "application/json"})
        with urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode())
    except Exception as e:
        logger.exception(f"Nightmarket search failed: {e}")
        return [{"error": str(e)}]


def nightmarket_service_details(endpoint_id: str) -> Dict:
    """Get full details for a specific Nightmarket service including request/response examples.

    Args:
        endpoint_id: The service ID from nightmarket_search results

    Returns:
        Service details including name, description, method, price, request/response examples
    """
    try:
        safe_id = _validate_endpoint_id(endpoint_id)
        url = f"{NIGHTMARKET_BASE_URL}/marketplace/{safe_id}"
        req = Request(url, headers={"Accept": "application/json"})
        with urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode())
    except Exception as e:
        logger.exception(f"Nightmarket service details failed: {e}")
        return {"error": str(e)}


def nightmarket_call(
    endpoint_id: str,
    method: str = "GET",
    params: Optional[Dict] = None,
    body: Optional[Dict] = None,
    headers: Optional[Dict] = None,
    payment_signature: Optional[str] = None,
) -> Dict:
    """Call a Nightmarket API service. First call returns 402 with payment details.
    After paying (e.g., via CrowPay), retry with the payment_signature.

    Args:
        endpoint_id: The service endpoint ID
        method: HTTP method — GET, POST, PUT, PATCH, DELETE (default: GET)
        params: Query parameters for the request URL (optional)
        body: Request body for POST/PUT/PATCH (optional)
        headers: Additional HTTP headers (optional)
        payment_signature: Base64-encoded x402 payment proof from CrowPay (optional)

    Returns:
        API response, or 402 payment details if unpaid
    """
    try:
        safe_id = _validate_endpoint_id(endpoint_id)
        url = f"{NIGHTMARKET_BASE_URL}/x402/{safe_id}"
        if params:
            url = f"{url}?{urlencode(params, doseq=True)}"

        req_headers = {"Accept": "application/json"}
        if headers:
            # Filter to safe headers only
            for k, v in headers.items():
                if k.lower() in _SAFE_HEADERS:
                    req_headers[k] = v
        if payment_signature:
            req_headers["payment-signature"] = payment_signature

        data = None
        if body and method.upper() in ("POST", "PUT", "PATCH"):
            data = json.dumps(body).encode()
            req_headers["Content-Type"] = "application/json"

        req = Request(url, data=data, headers=req_headers, method=method.upper())
        try:
            with urlopen(req, timeout=30) as resp:
                result = json.loads(resp.read().decode())
                return result
        except HTTPError as e:
            if e.code == 402:
                raw_body = e.read()
                try:
                    payment_info = json.loads(raw_body.decode()) if raw_body else {}
                except (json.JSONDecodeError, UnicodeDecodeError):
                    payment_info = {"raw_body": raw_body.decode(errors="replace")} if raw_body else {}
                payment_header = e.headers.get("PAYMENT-REQUIRED", "")
                return {
                    "status": 402,
                    "message": "Payment required. Use CrowPay to authorize payment, then retry with payment_signature.",
                    "payment_required": payment_info,
                    "payment_header": payment_header,
                }
            raise
    except Exception as e:
        logger.exception(f"Nightmarket call failed: {e}")
        return {"error": str(e)}
