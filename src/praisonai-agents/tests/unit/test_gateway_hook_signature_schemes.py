"""Signature schemes + replay window for inbound hooks (Issue #5866)."""

import base64
import hashlib
import hmac
import time

import pytest

from praisonaiagents.gateway import HookConfig, verify_webhook_signature

SECRET = "whsec"
BODY = b'{"id":"evt_1"}'


def _hex(basis: bytes) -> str:
    return hmac.new(SECRET.encode(), basis, hashlib.sha256).hexdigest()


def test_default_scheme_unchanged_without_timestamp():
    hook = HookConfig(path="gh", secret=SECRET, signature_prefix="sha256=")
    assert hook.signature_scheme == "hmac_hex"
    # Body-only hooks never apply the freshness window (backward compatible).
    assert hook.verify_signature(BODY, {"X-Hub-Signature-256": "sha256=" + _hex(BODY)})


def test_hmac_base64():
    sig = base64.b64encode(hmac.new(SECRET.encode(), BODY, hashlib.sha256).digest()).decode()
    hook = HookConfig(path="b", secret=SECRET, signature_header="X-Sig",
                      signature_scheme="hmac_base64")
    assert hook.verify_signature(BODY, {"X-Sig": sig})
    assert not hook.verify_signature(BODY, {"X-Sig": _hex(BODY)})


def test_hmac_timestamped_fresh_and_stale():
    hook = HookConfig(path="t", secret=SECRET, signature_header="X-Sig",
                      signature_scheme="hmac_timestamped", timestamp_header="X-Ts")
    now = str(int(time.time()))
    sig = _hex(f"{now}.".encode() + BODY)
    assert hook.verify_signature(BODY, {"X-Sig": sig, "X-Ts": now})
    # Tampered timestamp breaks the signature.
    assert not hook.verify_signature(BODY, {"X-Sig": sig, "X-Ts": str(int(now) + 1)})
    # Stale (replayed) request is rejected even with a valid signature.
    old = str(int(time.time()) - 3600)
    assert not hook.verify_signature(BODY, {"X-Sig": _hex(f"{old}.".encode() + BODY), "X-Ts": old})
    # Missing timestamp is fail-closed.
    assert not hook.verify_signature(BODY, {"X-Sig": sig})


def test_structured_stripe_style():
    hook = HookConfig(path="stripe", secret=SECRET, signature_scheme="structured",
                      signature_header="Stripe-Signature", timestamp_header="Stripe-Signature")
    now = str(int(time.time()))
    good = _hex(f"{now}.".encode() + BODY)
    header = f"t={now},v1=deadbeef,v1={good}"
    assert hook.verify_signature(BODY, {"Stripe-Signature": header})
    # Works without timestamp_header too (t= read from the signature header).
    hook2 = HookConfig(path="s2", secret=SECRET, signature_scheme="structured",
                       signature_header="Stripe-Signature")
    assert hook2.verify_signature(BODY, {"Stripe-Signature": header})
    old = str(int(time.time()) - 3600)
    stale = f"t={old},v1={_hex(f'{old}.'.encode() + BODY)}"
    assert not hook.verify_signature(BODY, {"Stripe-Signature": stale})
    assert not hook.verify_signature(BODY, {"Stripe-Signature": f"t={now}"})


def test_tolerance_zero_disables_freshness():
    old = str(int(time.time()) - 3600)
    sig = _hex(f"{old}.".encode() + BODY)
    assert verify_webhook_signature(SECRET, BODY, sig, scheme="hmac_timestamped", timestamp=old)
    assert not verify_webhook_signature(SECRET, BODY, sig, scheme="hmac_timestamped",
                                        timestamp=old, tolerance_seconds=300)


def test_unknown_scheme_rejected():
    with pytest.raises(ValueError):
        HookConfig(path="x", signature_scheme="nope")
    assert not verify_webhook_signature(SECRET, BODY, _hex(BODY), scheme="nope")


def test_round_trip_new_fields():
    hook = HookConfig.from_dict({"path": "s", "secret": SECRET, "signature_scheme": "structured",
                                 "timestamp_header": "Stripe-Signature",
                                 "signature_tolerance_seconds": 60})
    data = hook.to_dict()
    assert data["signature_scheme"] == "structured"
    assert data["timestamp_header"] == "Stripe-Signature"
    assert data["signature_tolerance_seconds"] == 60
    assert "signature_scheme" not in hook.metadata


def test_timestamp_header_requires_signed_timestamp_scheme():
    # An unsigned timestamp header would let an old body+signature be replayed
    # with a fresh timestamp, so the combination is refused up front.
    for scheme in ("hmac_hex", "hmac_base64"):
        with pytest.raises(ValueError, match="timestamp_header"):
            HookConfig(path="x", secret=SECRET, signature_scheme=scheme,
                       timestamp_header="X-Ts")


def test_tolerance_coerced_and_negative_rejected():
    hook = HookConfig.from_dict({"path": "q", "secret": SECRET,
                                 "signature_header": "X-Sig",
                                 "signature_scheme": "hmac_timestamped",
                                 "timestamp_header": "X-Ts",
                                 "signature_tolerance_seconds": "300"})
    assert hook.signature_tolerance_seconds == 300
    now = str(int(time.time()))
    assert hook.verify_signature(BODY, {"X-Sig": _hex(f"{now}.".encode() + BODY), "X-Ts": now})
    with pytest.raises(ValueError, match=">= 0"):
        HookConfig(path="n", signature_tolerance_seconds=-1)
    with pytest.raises(ValueError, match="integer"):
        HookConfig(path="n", signature_tolerance_seconds="soon")
