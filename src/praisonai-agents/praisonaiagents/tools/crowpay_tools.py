"""CrowPay agent payment tools — gives AI agents a wallet to pay for APIs and services.

Usage:
from praisonaiagents.tools import crowpay_setup, crowpay_authorize, crowpay_authorize_card, crowpay_poll_status

# Set up a new agent wallet
wallet = crowpay_setup()

# Authorize an x402 payment (after getting a 402 response)
result = crowpay_authorize(api_key, payment_required_body, "ServiceName", "Why paying")

# Authorize a credit card payment
result = crowpay_authorize_card(api_key, 500, "OpenAI", "GPT-4 credits")

# Poll for human approval status
status = crowpay_poll_status(api_key, approval_id)

CrowPay (https://crowpay.ai) provides managed wallets for AI agents with spending rules,
human approval workflows, and audit trails. Supports x402 (USDC on Base) and credit card
payments via the x402 payment protocol.
"""

from typing import Dict, Optional
import logging
import json

logger = logging.getLogger(__name__)

CROWPAY_BASE_URL = "https://api.crowpay.ai"


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
        from urllib.request import urlopen, Request

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
        logger.error(f"CrowPay setup failed: {e}")
        return {"error": str(e)}


def crowpay_authorize(
    api_key: str,
    payment_required: Dict,
    merchant: str,
    reason: str,
    platform: str = "PraisonAI",
    service: str = "",
) -> Dict:
    """Authorize an x402 payment. Forward the 402 response body from an API here.

    Args:
        api_key: CrowPay API key (crow_sk_...)
        payment_required: The full HTTP 402 response body from the x402 API
        merchant: Human-readable name of the service
        reason: Why the payment is needed
        platform: Which platform is making the request (default: PraisonAI)
        service: What service/product the payment is for (optional)

    Returns:
        On 200: signed payment payload (use base64-encoded as payment-signature header)
        On 202: status=pending with approvalId (poll with crowpay_poll_status)
        On 403: denied with reason
    """
    try:
        from urllib.request import urlopen, Request
        from urllib.error import HTTPError

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
                "X-API-Key": api_key,
            },
            method="POST",
        )
        try:
            with urlopen(req, timeout=15) as resp:
                return json.loads(resp.read().decode())
        except HTTPError as e:
            resp_body = e.read().decode() if e.read else "{}"
            result = json.loads(resp_body)
            result["_status_code"] = e.code
            return result
    except Exception as e:
        logger.error(f"CrowPay authorize failed: {e}")
        return {"error": str(e)}


def crowpay_authorize_card(
    api_key: str,
    amount_cents: int,
    merchant: str,
    reason: str,
    currency: str = "usd",
    platform: str = "PraisonAI",
    service: str = "",
) -> Dict:
    """Request a credit card payment via CrowPay.

    Args:
        api_key: CrowPay API key (crow_sk_...)
        amount_cents: Amount in cents (1000 = $10.00)
        merchant: Merchant name
        reason: Why the payment is needed
        currency: Currency code (default: usd)
        platform: Which platform is making the request (default: PraisonAI)
        service: What service/product the payment is for (optional)

    Returns:
        On 200: approved=True with sptToken (Stripe Shared Payment Token)
        On 202: status=pending with approvalId
        On 403: denied with reason
    """
    try:
        from urllib.request import urlopen, Request
        from urllib.error import HTTPError

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
                "X-API-Key": api_key,
            },
            method="POST",
        )
        try:
            with urlopen(req, timeout=15) as resp:
                return json.loads(resp.read().decode())
        except HTTPError as e:
            resp_body = e.read().decode() if e.read else "{}"
            result = json.loads(resp_body)
            result["_status_code"] = e.code
            return result
    except Exception as e:
        logger.error(f"CrowPay card authorize failed: {e}")
        return {"error": str(e)}


def crowpay_poll_status(api_key: str, approval_id: str) -> Dict:
    """Poll for the status of a pending CrowPay approval.

    Call every 3 seconds until you get a terminal state.

    Args:
        api_key: CrowPay API key (crow_sk_...)
        approval_id: The approvalId from a 202 response

    Returns:
        Status dict. Terminal states: payload/sptToken present (approved),
        status=denied, status=timeout, status=failed
    """
    try:
        from urllib.request import urlopen, Request

        url = f"{CROWPAY_BASE_URL}/authorize/status?id={approval_id}"
        req = Request(url, headers={"X-API-Key": api_key})
        with urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode())
    except Exception as e:
        logger.error(f"CrowPay poll failed: {e}")
        return {"error": str(e)}


def crowpay_settle(api_key: str, transaction_id: str, tx_hash: str) -> Dict:
    """Report x402 payment settlement. Idempotent — safe to call multiple times.

    Args:
        api_key: CrowPay API key (crow_sk_...)
        transaction_id: Transaction ID from the authorize response
        tx_hash: On-chain transaction hash

    Returns:
        Success confirmation
    """
    try:
        from urllib.request import urlopen, Request

        data = json.dumps({"transactionId": transaction_id, "txHash": tx_hash}).encode()
        req = Request(
            f"{CROWPAY_BASE_URL}/settle",
            data=data,
            headers={
                "Content-Type": "application/json",
                "X-API-Key": api_key,
            },
            method="POST",
        )
        with urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode())
    except Exception as e:
        logger.error(f"CrowPay settle failed: {e}")
        return {"error": str(e)}
