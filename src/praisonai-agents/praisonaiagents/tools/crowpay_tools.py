"""CrowPay agent payment tools — gives AI agents a wallet to pay for APIs and services.

Usage:
from praisonaiagents.tools import crowpay_setup, crowpay_authorize, crowpay_authorize_card, crowpay_poll_status

# Set up a new agent wallet
wallet = crowpay_setup()

# Authorize an x402 payment (after getting a 402 response)
result = crowpay_authorize(payment_required_body, "ServiceName", "Why paying")

# Authorize a credit card payment
result = crowpay_authorize_card(500, "OpenAI", "GPT-4 credits")

# Poll for human approval status
status = crowpay_poll_status(approval_id)

CrowPay (https://crowpay.ai) provides managed wallets for AI agents with spending rules,
human approval workflows, and audit trails. Supports x402 (USDC on Base) and credit card
payments via the x402 payment protocol.

Set CROWPAY_API_KEY environment variable to avoid passing keys in function arguments.
"""

from typing import Dict, Optional
import logging
import json
import os
from urllib.request import urlopen, Request
from urllib.error import HTTPError
from urllib.parse import urlencode, quote

logger = logging.getLogger(__name__)

CROWPAY_BASE_URL = "https://api.crowpay.ai"


def _get_api_key(explicit_key: Optional[str] = None) -> str:
    """Get API key from explicit argument or CROWPAY_API_KEY environment variable."""
    key = explicit_key or os.environ.get("CROWPAY_API_KEY", "")
    if not key:
        raise ValueError("No API key provided. Set CROWPAY_API_KEY env var or pass api_key argument.")
    return key


def _parse_http_error(e: HTTPError) -> Dict:
    """Safely parse HTTP error responses, preserving status code."""
    raw = e.read().decode("utf-8", errors="replace") if e.fp else ""
    try:
        payload = json.loads(raw) if raw else {}
    except json.JSONDecodeError:
        payload = {"error": raw or str(e)}
    payload["_status_code"] = e.code
    return payload


def crowpay_setup(network: str = "eip155:8453") -> Dict:
    """Create a new agent wallet and API key via CrowPay.

    Returns apiKey (shown only once!), walletAddress, claimUrl, and fundingInstructions.
    The user must visit claimUrl to set spending rules.

    Args:
        network: CAIP-2 network ID (default: Base mainnet)

    Returns:
        Dict with apiKey, walletAddress, claimUrl, fundingInstructions
    """
    try:
        data = json.dumps({"network": network}).encode()
        req = Request(
            f"{CROWPAY_BASE_URL}/setup",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode())
    except Exception as e:
        logger.exception(f"CrowPay setup failed: {e}")
        return {"error": str(e)}


def crowpay_authorize(
    payment_required: Dict,
    merchant: str,
    reason: str,
    api_key: Optional[str] = None,
    platform: str = "PraisonAI",
    service: str = "",
) -> Dict:
    """Authorize an x402 payment. Forward the 402 response body from an API here.

    Args:
        payment_required: The full HTTP 402 response body from the x402 API
        merchant: Human-readable name of the service
        reason: Why the payment is needed
        api_key: CrowPay API key (optional if CROWPAY_API_KEY env var is set)
        platform: Which platform is making the request (default: PraisonAI)
        service: What service/product the payment is for (optional)

    Returns:
        On 200: signed payment payload (use base64-encoded as payment-signature header)
        On 202: status=pending with approvalId (poll with crowpay_poll_status)
        On 403: denied with reason
    """
    try:
        key = _get_api_key(api_key)

        body = {
            "paymentRequired": payment_required,
            "merchant": merchant,
            "reason": reason,
            "platform": platform,
        }
        if service:
            body["service"] = service

        data = json.dumps(body).encode()
        req = Request(
            f"{CROWPAY_BASE_URL}/authorize",
            data=data,
            headers={
                "Content-Type": "application/json",
                "X-API-Key": key,
            },
            method="POST",
        )
        try:
            with urlopen(req, timeout=15) as resp:
                return json.loads(resp.read().decode())
        except HTTPError as e:
            return _parse_http_error(e)
    except Exception as e:
        logger.exception(f"CrowPay authorize failed: {e}")
        return {"error": str(e)}


def crowpay_authorize_card(
    amount_cents: int,
    merchant: str,
    reason: str,
    api_key: Optional[str] = None,
    currency: str = "usd",
    platform: str = "PraisonAI",
    service: str = "",
) -> Dict:
    """Request a credit card payment via CrowPay.

    Args:
        amount_cents: Amount in cents (1000 = $10.00)
        merchant: Merchant name
        reason: Why the payment is needed
        api_key: CrowPay API key (optional if CROWPAY_API_KEY env var is set)
        currency: Currency code (default: usd)
        platform: Which platform is making the request (default: PraisonAI)
        service: What service/product the payment is for (optional)

    Returns:
        On 200: approved=True with sptToken (Stripe Shared Payment Token)
        On 202: status=pending with approvalId
        On 403: denied with reason
    """
    try:
        key = _get_api_key(api_key)

        body = {
            "amountCents": amount_cents,
            "merchant": merchant,
            "reason": reason,
            "currency": currency,
            "platform": platform,
        }
        if service:
            body["service"] = service

        data = json.dumps(body).encode()
        req = Request(
            f"{CROWPAY_BASE_URL}/authorize/card",
            data=data,
            headers={
                "Content-Type": "application/json",
                "X-API-Key": key,
            },
            method="POST",
        )
        try:
            with urlopen(req, timeout=15) as resp:
                return json.loads(resp.read().decode())
        except HTTPError as e:
            return _parse_http_error(e)
    except Exception as e:
        logger.exception(f"CrowPay card authorize failed: {e}")
        return {"error": str(e)}


def crowpay_poll_status(approval_id: str, api_key: Optional[str] = None) -> Dict:
    """Poll for the status of a pending CrowPay approval.

    Call every 3 seconds until you get a terminal state.

    Args:
        approval_id: The approvalId from a 202 response
        api_key: CrowPay API key (optional if CROWPAY_API_KEY env var is set)

    Returns:
        Status dict. Terminal states: payload/sptToken present (approved),
        status=denied, status=timeout, status=failed
    """
    try:
        key = _get_api_key(api_key)

        url = f"{CROWPAY_BASE_URL}/authorize/status?{urlencode({'id': approval_id})}"
        req = Request(url, headers={"X-API-Key": key})
        with urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode())
    except Exception as e:
        logger.exception(f"CrowPay poll failed: {e}")
        return {"error": str(e)}


def crowpay_settle(transaction_id: str, tx_hash: str, api_key: Optional[str] = None) -> Dict:
    """Report x402 payment settlement. Idempotent — safe to call multiple times.

    Args:
        transaction_id: Transaction ID from the authorize response
        tx_hash: On-chain transaction hash
        api_key: CrowPay API key (optional if CROWPAY_API_KEY env var is set)

    Returns:
        Success confirmation
    """
    try:
        key = _get_api_key(api_key)

        data = json.dumps({"transactionId": transaction_id, "txHash": tx_hash}).encode()
        req = Request(
            f"{CROWPAY_BASE_URL}/settle",
            data=data,
            headers={
                "Content-Type": "application/json",
                "X-API-Key": key,
            },
            method="POST",
        )
        with urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode())
    except Exception as e:
        logger.exception(f"CrowPay settle failed: {e}")
        return {"error": str(e)}
