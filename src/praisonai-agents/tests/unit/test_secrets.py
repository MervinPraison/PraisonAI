"""Unit tests for first-class secret references (Issue #3102).

Covers the core ``SecretRef`` type, the ``env`` / ``file`` / ``exec`` resolvers,
availability reporting, backward-compatible plaintext / ``${ENV}`` handling, and
the log-redaction registry — all stdlib-only, protocol-first core surface.
"""

import os

import pytest

from praisonaiagents.secrets import (
    AVAILABLE,
    MISSING,
    UNAVAILABLE,
    DefaultSecretResolver,
    EgressGuardProtocol,
    OutboundRedactor,
    SecretRef,
    SecretResolution,
    SecretResolver,
    desentinelize,
    has_sentinel,
    is_secret_ref,
    redact_outbound,
    redact_secrets,
    register_resolver,
    register_secret_for_redaction,
    resolve_secret,
    sentinelize,
)


def test_secret_ref_validates_source():
    with pytest.raises(ValueError):
        SecretRef(source="bogus", id="x")


def test_secret_ref_requires_id():
    with pytest.raises(ValueError):
        SecretRef(source="env", id="")


def test_secret_ref_repr_hides_no_value():
    ref = SecretRef(source="file", id="/run/secrets/token")
    assert "token" in repr(ref)  # id is a locator, safe to show
    assert repr(ref).startswith("SecretRef(")


def test_default_resolver_env_available(monkeypatch):
    monkeypatch.setenv("MY_TOKEN_3102", "s3cr3t-value")
    res = DefaultSecretResolver().resolve(SecretRef("env", "MY_TOKEN_3102"))
    assert res.status == AVAILABLE
    assert res.value == "s3cr3t-value"
    assert res.available is True


def test_default_resolver_env_missing(monkeypatch):
    monkeypatch.delenv("NOPE_3102", raising=False)
    res = DefaultSecretResolver().resolve(SecretRef("env", "NOPE_3102"))
    assert res.status == MISSING
    assert res.value is None


def test_default_resolver_env_empty_is_unavailable(monkeypatch):
    monkeypatch.setenv("EMPTY_3102", "   ")
    res = DefaultSecretResolver().resolve(SecretRef("env", "EMPTY_3102"))
    assert res.status == UNAVAILABLE


def test_default_resolver_file(tmp_path):
    p = tmp_path / "token"
    p.write_text("file-secret\n")
    res = DefaultSecretResolver().resolve(SecretRef("file", str(p)))
    assert res.status == AVAILABLE
    assert res.value == "file-secret"


def test_default_resolver_file_missing(tmp_path):
    res = DefaultSecretResolver().resolve(SecretRef("file", str(tmp_path / "nope")))
    assert res.status == MISSING


def test_default_resolver_exec():
    res = DefaultSecretResolver().resolve(
        SecretRef("exec", "python -c \"print('exec-secret')\"")
    )
    assert res.status == AVAILABLE
    assert res.value == "exec-secret"


def test_default_resolver_exec_nonzero():
    res = DefaultSecretResolver().resolve(SecretRef("exec", "python -c \"import sys; sys.exit(3)\""))
    assert res.status == UNAVAILABLE


def test_resolve_secret_plaintext_backward_compatible():
    res = resolve_secret("123456:ABCdef")
    assert res.available
    assert res.value == "123456:ABCdef"


def test_resolve_secret_env_placeholder(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN_3102", "tg-token")
    res = resolve_secret("${TELEGRAM_BOT_TOKEN_3102}")
    assert res.available
    assert res.value == "tg-token"


def test_resolve_secret_env_placeholder_missing(monkeypatch):
    monkeypatch.delenv("MISSING_ENV_3102", raising=False)
    res = resolve_secret("${MISSING_ENV_3102}")
    assert res.status == MISSING


def test_resolve_secret_dict_reference(tmp_path):
    p = tmp_path / "tok"
    p.write_text("dict-ref-secret")
    res = resolve_secret({"source": "file", "id": str(p)})
    assert res.available
    assert res.value == "dict-ref-secret"


def test_resolve_secret_registers_redaction(tmp_path):
    p = tmp_path / "tok"
    p.write_text("redact-me-9999")
    resolve_secret({"source": "file", "id": str(p)})
    assert redact_secrets("token is redact-me-9999 here") == "token is [REDACTED] here"


def test_is_secret_ref():
    assert is_secret_ref(SecretRef("env", "X"))
    assert is_secret_ref({"source": "env", "id": "X"})
    assert not is_secret_ref("plaintext")
    assert not is_secret_ref({"other": "key"})


def test_redaction_ignores_short_values():
    register_secret_for_redaction("ab")  # too short
    assert redact_secrets("ab cd") == "ab cd"


def test_redaction_longest_first():
    register_secret_for_redaction("abcd")
    register_secret_for_redaction("abcdefgh")
    assert redact_secrets("value=abcdefgh") == "value=[REDACTED]"


def test_custom_resolver_registration():
    class _Fixed(SecretResolver):
        def resolve(self, ref):
            return SecretResolution(AVAILABLE, value="from-custom")

    register_resolver("env", _Fixed())
    try:
        res = resolve_secret(SecretRef("env", "IGNORED"))
        assert res.value == "from-custom"
    finally:
        # Reset the registry entry so we don't leak into other tests.
        import praisonaiagents.secrets as s
        s._resolvers.pop("env", None)


# ── Outbound redaction (Issue #5055) ──────────────────────────────────────


def test_redact_outbound_masks_registered_secret():
    register_secret_for_redaction("sk-registered-outbound-1234")
    out = redact_outbound("your key is sk-registered-outbound-1234 done")
    assert out == "your key is [REDACTED] done"


def test_redact_outbound_masks_unregistered_credential_shapes():
    # None of these are registered; they are caught purely by shape.
    assert "AKIA" not in redact_outbound("id AKIAIOSFODNN7EXAMPLE here")
    assert "sk-" not in redact_outbound("key sk-abcDEF123456ghiJKL789 end")
    ghp = "found ghp_" + "a" * 36 + " token"
    assert "ghp_" not in redact_outbound(ghp)


def test_redact_outbound_masks_private_key_block():
    pem = (
        "before -----BEGIN RSA PRIVATE KEY-----\n"
        "MIIBmid...line\n"
        "-----END RSA PRIVATE KEY-----after"
    )
    out = redact_outbound(pem)
    assert "PRIVATE KEY" not in out
    assert "before" in out and "after" in out


def test_redact_outbound_leaves_ordinary_text_unchanged():
    text = "The meeting is at 3pm in room 1234, bring your laptop."
    assert redact_outbound(text) == text


def test_redact_outbound_handles_empty_and_none():
    assert redact_outbound("") == ""
    assert redact_outbound(None) is None


def test_outbound_redactor_protocol_is_runtime_checkable():
    class _R:
        def redact(self, text):
            return text

    assert isinstance(_R(), OutboundRedactor)

    class _NotR:
        pass

    assert not isinstance(_NotR(), OutboundRedactor)


# ── Secret sentinelisation (Issue #5722) ──────────────────────────────────


def test_sentinelize_replaces_plaintext_with_opaque_token():
    secret = "super-secret-egress-value-5722"
    token = sentinelize(secret)
    assert token != secret
    assert secret not in token
    assert token.startswith("oc-sent-")


def test_sentinelize_is_stable_per_process():
    secret = "stable-token-secret-5722"
    assert sentinelize(secret) == sentinelize(secret)


def test_sentinelize_hides_short_secrets_too():
    # A short PIN/password must be hidden just like a long key — the opaque,
    # random token never collides with ordinary text, so there is no minimum
    # length. Only empty / non-string values pass through verbatim.
    for short in ("1", "ab", "pin"):
        token = sentinelize(short)
        assert token != short
        assert token.startswith("oc-sent-")
        assert has_sentinel(f"x={token}") is True
        assert desentinelize(f"x={token}") == f"x={short}"
    assert sentinelize("") == ""


def test_desentinelize_only_touches_tokens_in_the_text():
    # Minting many secrets must not slow a request that carries just one token:
    # desentinelize looks up only the token shapes present in the input.
    kept = [sentinelize(f"many-secret-{i}-5722") for i in range(50)]
    one = sentinelize("just-this-one-secret-5722")
    out = desentinelize(f"Authorization: Bearer {one}")
    assert out == "Authorization: Bearer just-this-one-secret-5722"
    # Unrelated tokens are not substituted into the text.
    for other in kept:
        assert other not in out


def test_desentinelize_ignores_unknown_token_shaped_strings():
    forged = "oc-sent-" + "0" * 32
    assert desentinelize(f"k={forged}") == f"k={forged}"
    assert has_sentinel(f"k={forged}") is False


def test_desentinelize_round_trips_only_on_egress():
    secret = "round-trip-secret-5722"
    token = sentinelize(secret)
    # Model-visible text carries only the sentinel.
    model_text = f"Authorization: Bearer {token}"
    assert secret not in model_text
    # Egress guard substitutes the real value back on the wire.
    assert desentinelize(model_text) == f"Authorization: Bearer {secret}"


def test_desentinelize_leaves_text_without_sentinel_unchanged():
    assert desentinelize("no sentinel here") == "no sentinel here"
    assert desentinelize("") == ""
    assert desentinelize(None) is None


def test_has_sentinel_detects_minted_token():
    token = sentinelize("detect-me-secret-5722")
    assert has_sentinel(f"k={token}") is True
    assert has_sentinel("k=plain-value") is False
    assert has_sentinel("") is False


def test_sentinelized_secret_is_registered_for_redaction():
    secret = "redact-via-sentinel-5722"
    sentinelize(secret)
    assert redact_secrets(f"leaked {secret} here") == "leaked [REDACTED] here"


def test_egress_guard_protocol_is_runtime_checkable():
    class _Guard:
        def sentinel_for(self, ref):
            return "oc-sent-x"

        def allow_egress(self, host, ref):
            return True

    assert isinstance(_Guard(), EgressGuardProtocol)

    class _NotGuard:
        pass

    assert not isinstance(_NotGuard(), EgressGuardProtocol)
