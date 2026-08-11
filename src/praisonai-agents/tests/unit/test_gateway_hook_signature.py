"""Unit tests for the inbound hook contract extensions (Issue #3165).

Covers the additive, pure core-side surface added to ``HookConfig``:

- ``verify_webhook_signature`` / ``HookConfig.verify_signature`` — fail-closed
  HMAC verification over the raw body (prefix-aware, algo-aware).
- ``HookConfig.event_allowed`` — event-type filtering from a header or payload,
  including GitHub-style ``base.action`` sub-typing.
- ``deliver_only`` and the round-trip of all new fields through
  ``to_dict``/``from_dict`` (secrets redacted).
"""

import hmac

import pytest

from praisonaiagents.gateway import HookConfig, verify_webhook_signature


def _sign(secret: str, body: bytes, *, algo: str = "sha256", prefix: str = "") -> str:
    return f"{prefix}{hmac.new(secret.encode(), body, algo).hexdigest()}"


def test_verify_webhook_signature_valid_and_invalid():
    secret = "s3cr3t"
    body = b'{"action":"opened"}'
    good = _sign(secret, body, prefix="sha256=")
    assert verify_webhook_signature(secret, body, good, prefix="sha256=") is True
    assert verify_webhook_signature(secret, body, "sha256=deadbeef", prefix="sha256=") is False
    # fail-closed on missing secret/signature and unknown algorithm
    assert verify_webhook_signature(None, body, good) is False
    assert verify_webhook_signature(secret, body, None) is False
    assert verify_webhook_signature(secret, body, good, algo="not-a-real-algo") is False


def test_verify_signature_reads_configured_header():
    secret = "top"
    body = b'{"x":1}'
    hook = HookConfig(
        path="github",
        secret=secret,
        signature_header="X-Hub-Signature-256",
        signature_prefix="sha256=",
    )
    sig = _sign(secret, body, prefix="sha256=")
    assert hook.verify_signature(body, {"X-Hub-Signature-256": sig}) is True
    assert hook.verify_signature(body, {"x-hub-signature-256": sig}) is True  # case-insensitive
    assert hook.verify_signature(body, {}) is False  # missing header, fail-closed


def test_verify_signature_passthrough_when_no_secret():
    # A hook without ``secret`` behaves exactly as before: no verification.
    hook = HookConfig(path="open")
    assert hook.verify_signature(b"anything", {}) is True


def test_event_filter_github_base_action():
    hook = HookConfig(
        path="gh",
        events=["issues.opened", "pull_request.opened"],
        event_header="X-GitHub-Event",
    )
    headers = {"X-GitHub-Event": "issues"}
    assert hook.event_allowed({"action": "opened"}, headers) is True
    assert hook.event_allowed({"action": "closed"}, headers) is False
    assert hook.event_allowed({"action": "created"}, {"X-GitHub-Event": "star"}) is False


def test_event_filter_payload_path_and_no_filter():
    hook = HookConfig(path="stripe", events=["invoice.payment_failed"], event_header="type")
    assert hook.event_allowed({"type": "invoice.payment_failed"}) is True
    assert hook.event_allowed({"type": "invoice.paid"}) is False
    # no ``events`` configured -> everything passes
    assert HookConfig(path="any").event_allowed({"type": "whatever"}) is True


def test_events_string_is_coerced_to_list():
    assert HookConfig(path="p", events="push").events == ["push"]


def test_deliver_only_and_roundtrip_redacts_secrets():
    hook = HookConfig(
        path="deploy",
        deliver_only=True,
        deliver_to="telegram:ops",
        secret="hmac",
        signature_header="X-Signature",
        events=["deploy.done"],
        message="deployed {version}",
    )
    assert hook.deliver_only is True
    assert hook.resolve_message({"version": "1.2"}) == "deployed 1.2"

    d = hook.to_dict()
    assert d["secret"] == "***"  # never leak the signing secret
    assert d["deliver_only"] is True
    assert d["events"] == ["deploy.done"]

    rebuilt = HookConfig.from_dict({**d, "secret": "hmac"})
    assert rebuilt.deliver_only is True
    assert rebuilt.events == ["deploy.done"]
    assert rebuilt.signature_header == "X-Signature"
    assert rebuilt.signature_algo == "sha256"


def test_event_filter_missing_action_fails_closed():
    # A namespaced filter (``issues.opened``) must NOT admit a bare ``issues``
    # delivery when the payload omits ``action`` — fail-closed (#3166 review).
    hook = HookConfig(path="gh", events=["issues.opened"], event_header="X-GitHub-Event")
    headers = {"X-GitHub-Event": "issues"}
    assert hook.event_allowed({}, headers) is False
    assert hook.event_allowed({"action": "opened"}, headers) is True


def test_secret_without_header_gets_default_header():
    # A configured secret with no explicit header defaults to the GitHub-style
    # header instead of rejecting every request (#3166 review).
    secret = "s"
    body = b'{"a":1}'
    hook = HookConfig(path="gh", secret=secret, signature_prefix="sha256=")
    assert hook.signature_header == "X-Hub-Signature-256"
    sig = _sign(secret, body, prefix="sha256=")
    assert hook.verify_signature(body, {"X-Hub-Signature-256": sig}) is True


def test_backward_compatible_auth_only_hook():
    # An existing hook with only ``auth`` keeps today's shape: no secret,
    # no events, no deliver_only.
    hook = HookConfig(path="legacy", auth="bearer-token", message="{msg}")
    assert hook.secret is None
    assert hook.events is None
    assert hook.deliver_only is False
    assert hook.verify_signature(b"{}", {}) is True
    assert hook.event_allowed({}, {}) is True
