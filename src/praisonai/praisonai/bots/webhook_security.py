"""Shared webhook verification helpers for bot integrations.

Provides a single, fail-closed contract for inbound webhook authenticity so
adapters stop re-implementing HMAC comparison with divergent failure modes.

Public API:
  - webhooks_require_verification() -> bool
  - verify_hmac(secret, body, signature, *, digest="sha256", prefix=None) -> bool
  - HmacWebhookVerifier — a reusable WebhookVerifier implementation
  - enforce_webhook_verification(...) — central, fail-closed gate for ingress
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
from typing import Iterable, Mapping, Optional, Union

logger = logging.getLogger(__name__)

__all__ = [
    "webhooks_require_verification",
    "verify_hmac",
    "HmacWebhookVerifier",
    "enforce_webhook_verification",
]


def webhooks_require_verification() -> bool:
    """Return True unless explicit dev override disables signature checks."""
    return os.environ.get("PRAISONAI_INSECURE_WEBHOOKS", "").lower() not in (
        "true",
        "1",
        "yes",
    )


def verify_hmac(
    secret: Union[str, bytes],
    body: Union[str, bytes],
    signature: Optional[str],
    *,
    digest: str = "sha256",
    prefix: Optional[str] = None,
) -> bool:
    """Constant-time HMAC verification of a webhook body against a signature.

    Args:
        secret: Shared signing secret.
        body: Raw request body bytes (or str, encoded as utf-8).
        signature: Signature header value provided by the platform.
        digest: Hash algorithm name (e.g. "sha256", "sha1").
        prefix: Optional signature prefix to strip/compare (e.g. "sha256=").

    Returns:
        True only if a non-empty signature matches the computed HMAC using a
        constant-time comparison. Fail-closed: missing secret or signature
        returns False.
    """
    if not secret or not signature:
        return False

    secret_bytes = secret.encode() if isinstance(secret, str) else secret
    body_bytes = body.encode() if isinstance(body, str) else body

    try:
        digestmod = getattr(hashlib, digest)
    except AttributeError:
        digestmod = lambda d=b"": hashlib.new(digest, d)  # noqa: E731

    computed = hmac.new(secret_bytes, body_bytes, digestmod).hexdigest()

    provided = signature
    if prefix:
        expected = f"{prefix}{computed}"
        return hmac.compare_digest(expected, provided)

    # Tolerate an "algo=" style prefix on the provided signature.
    if "=" in provided and provided.split("=", 1)[0].isalnum():
        provided = provided.split("=", 1)[1]

    return hmac.compare_digest(computed, provided)


def _first_header(headers: Mapping[str, str], names: Iterable[str]) -> Optional[str]:
    """Case-insensitive lookup of the first present header among ``names``."""
    lowered = {k.lower(): v for k, v in headers.items()}
    for name in names:
        value = lowered.get(name.lower())
        if value:
            return value
    return None


class HmacWebhookVerifier:
    """Reusable :class:`WebhookVerifier` backed by :func:`verify_hmac`.

    Adapters can construct this with their secret and the header name(s) that
    carry the signature instead of re-implementing crypto.

    Example::

        verifier = HmacWebhookVerifier(
            secret=app_secret,
            signature_headers=["X-Hub-Signature-256"],
            prefix="sha256=",
        )
        if verifier.verify(headers=request.headers, raw_body=body):
            ...
    """

    def __init__(
        self,
        secret: Union[str, bytes],
        *,
        signature_headers: Iterable[str],
        digest: str = "sha256",
        prefix: Optional[str] = None,
    ) -> None:
        self._secret = secret
        self._signature_headers = list(signature_headers)
        self._digest = digest
        self._prefix = prefix

    def verify(self, *, headers: Mapping[str, str], raw_body: bytes) -> bool:
        signature = _first_header(headers, self._signature_headers)
        return verify_hmac(
            self._secret,
            raw_body,
            signature,
            digest=self._digest,
            prefix=self._prefix,
        )


def enforce_webhook_verification(
    *,
    accepts_webhooks: bool,
    verifier: Optional["object"],
    headers: Mapping[str, str],
    raw_body: bytes,
    platform: str = "",
) -> bool:
    """Central, fail-closed gate for inbound webhooks.

    Returns True if the request may proceed, False if it must be rejected
    (typically with HTTP 401). Verification is required when the adapter
    declares it accepts webhooks, unless ``PRAISONAI_INSECURE_WEBHOOKS`` is
    explicitly set for local development.

    Args:
        accepts_webhooks: Whether this channel is webhook-based.
        verifier: An object exposing ``verify(*, headers, raw_body)`` or None.
        headers: Inbound request headers.
        raw_body: Raw request body bytes.
        platform: Platform name, for logging only.
    """
    if not accepts_webhooks:
        return True

    if not webhooks_require_verification():
        logger.warning(
            "PRAISONAI_INSECURE_WEBHOOKS set: skipping webhook verification for %s",
            platform or "unknown",
        )
        return True

    if verifier is None:
        logger.warning(
            "Webhook rejected for %s: no verifier configured (fail-closed)",
            platform or "unknown",
        )
        return False

    try:
        return bool(verifier.verify(headers=headers, raw_body=raw_body))
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("Webhook verification error for %s: %s", platform or "unknown", exc)
        return False
