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
    OutboundRedactor,
    SecretRef,
    SecretResolution,
    SecretResolver,
    is_secret_ref,
    redact_outbound,
    redact_secrets,
    register_resolver,
    register_secret_for_redaction,
    resolve_secret,
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
