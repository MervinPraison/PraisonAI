"""
First-class secret references for credential fields (Issue #3102).

Provides a lightweight, protocol-first contract so that any credential field
(bot token, Slack app token, WhatsApp verify token, API keys) can be sourced
from an environment variable, a mounted secret file, or a command / secret
manager — instead of being committed as plaintext or exposed as a process-wide
environment variable.

Design goals (kept deliberately lightweight — stdlib only, no heavy imports):

* ``SecretRef`` — a typed, immutable reference describing *where* a secret lives.
* ``SecretInput`` — ``str | SecretRef | dict`` so plaintext and ``${ENV}`` stay
  fully backward compatible; the reference form is purely additive.
* ``SecretResolver`` — a pluggable protocol; the built-in resolver handles the
  ``env`` / ``file`` / ``exec`` sources with the stdlib alone.
* ``register_secret_for_redaction`` / ``redact_secrets`` — a process-wide
  registry so resolved secret values can be scrubbed from logs and errors.

The wrapper (``praisonai``) and channel adapters may register additional
resolvers (e.g. a Vault / AWS / GCP secret-manager resolver) without importing
anything heavy into core.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional, Protocol, Union, runtime_checkable
import os
import threading

__all__ = [
    "SecretRef",
    "SecretInput",
    "SecretResolution",
    "SecretResolver",
    "DefaultSecretResolver",
    "resolve_secret",
    "register_resolver",
    "register_secret_for_redaction",
    "redact_secrets",
    "redact_outbound",
    "OutboundRedactor",
    "is_secret_ref",
]

# Valid built-in secret sources. ``exec`` runs a command whose stdout is the
# secret (e.g. a secret-manager CLI); it is opt-in and never runs for plaintext.
_VALID_SOURCES = ("env", "file", "exec")

# Availability states reported by a resolver / ``gateway doctor``.
AVAILABLE = "available"
UNAVAILABLE = "configured-but-unavailable"
MISSING = "missing"


@dataclass(frozen=True)
class SecretRef:
    """An immutable reference to a secret held outside the config file.

    Args:
        source: One of ``env`` (environment variable), ``file`` (a mounted
            secret file, e.g. ``/run/secrets/token``), or ``exec`` (a command
            whose stdout is the secret).
        id: The env var name, file path, or command line — interpreted per
            ``source``.
        provider: Optional free-form hint for custom resolvers (e.g. ``vault``).
    """

    source: str
    id: str
    provider: Optional[str] = None

    def __post_init__(self) -> None:
        if self.source not in _VALID_SOURCES:
            raise ValueError(
                f"Invalid secret source '{self.source}'. "
                f"Must be one of: {', '.join(_VALID_SOURCES)}"
            )
        if not self.id:
            raise ValueError("SecretRef.id must be a non-empty string")

    def __repr__(self) -> str:  # never leak the resolved value; id is a locator
        return f"SecretRef(source={self.source!r}, id={self.id!r})"


# A credential field accepts a plain string (plaintext or ``${ENV}``), a
# ``SecretRef``, or its dict form (``{"source": ..., "id": ...}``) from YAML.
SecretInput = Union[str, SecretRef, Dict[str, str]]


@dataclass(frozen=True)
class SecretResolution:
    """Outcome of resolving a :class:`SecretRef`.

    ``value`` is only populated when ``status == "available"``.
    """

    status: str
    value: Optional[str] = None
    detail: Optional[str] = None

    @property
    def available(self) -> bool:
        return self.status == AVAILABLE


@runtime_checkable
class SecretResolver(Protocol):
    """Pluggable resolver contract. Implementations must not raise on a merely
    unavailable secret — they return a :class:`SecretResolution` instead."""

    def resolve(self, ref: SecretRef) -> SecretResolution: ...


class DefaultSecretResolver:
    """Stdlib-only resolver for the ``env`` / ``file`` / ``exec`` sources."""

    def resolve(self, ref: SecretRef) -> SecretResolution:
        if ref.source == "env":
            return self._resolve_env(ref)
        if ref.source == "file":
            return self._resolve_file(ref)
        if ref.source == "exec":
            return self._resolve_exec(ref)
        return SecretResolution(MISSING, detail=f"unknown source {ref.source!r}")

    @staticmethod
    def _resolve_env(ref: SecretRef) -> SecretResolution:
        raw = os.environ.get(ref.id)
        if raw is None:
            return SecretResolution(MISSING, detail=f"env var {ref.id!r} not set")
        raw = raw.strip()
        if not raw:
            return SecretResolution(UNAVAILABLE, detail=f"env var {ref.id!r} empty")
        return SecretResolution(AVAILABLE, value=raw)

    @staticmethod
    def _resolve_file(ref: SecretRef) -> SecretResolution:
        if not os.path.exists(ref.id):
            return SecretResolution(MISSING, detail=f"file {ref.id!r} not found")
        try:
            with open(ref.id, "r", encoding="utf-8") as fh:
                raw = fh.read().strip()
        except OSError as exc:
            return SecretResolution(UNAVAILABLE, detail=f"cannot read {ref.id!r}: {exc}")
        if not raw:
            return SecretResolution(UNAVAILABLE, detail=f"file {ref.id!r} empty")
        return SecretResolution(AVAILABLE, value=raw)

    @staticmethod
    def _resolve_exec(ref: SecretRef) -> SecretResolution:
        import shlex
        import subprocess

        try:
            argv = shlex.split(ref.id)
        except ValueError as exc:
            return SecretResolution(UNAVAILABLE, detail=f"bad command {ref.id!r}: {exc}")
        if not argv:
            return SecretResolution(MISSING, detail="empty command")
        try:
            proc = subprocess.run(
                argv,
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            return SecretResolution(UNAVAILABLE, detail=f"command failed: {exc}")
        if proc.returncode != 0:
            return SecretResolution(
                UNAVAILABLE,
                detail=f"command exited {proc.returncode}",
            )
        raw = (proc.stdout or "").strip()
        if not raw:
            return SecretResolution(UNAVAILABLE, detail="command produced no output")
        return SecretResolution(AVAILABLE, value=raw)


# ────────────────────────────────────────────────────────────────────────────
# Resolver registry — wrapper / adapters register extra sources by name.
# ────────────────────────────────────────────────────────────────────────────

_default_resolver = DefaultSecretResolver()
_resolvers: Dict[str, SecretResolver] = {}
_resolvers_lock = threading.Lock()


def register_resolver(source: str, resolver: SecretResolver) -> None:
    """Register a custom resolver for a source name (e.g. ``vault``).

    Custom sources extend :data:`SecretRef` beyond the built-in three; the
    ``SecretRef`` validation still applies, so use this together with a
    ``provider`` hint or by resolving ``exec``-style commands.
    """
    with _resolvers_lock:
        _resolvers[source] = resolver


def _pick_resolver(ref: SecretRef) -> SecretResolver:
    with _resolvers_lock:
        resolver = _resolvers.get(ref.provider or "") or _resolvers.get(ref.source)
    return resolver or _default_resolver


def resolve_secret(
    value: SecretInput,
    *,
    resolver: Optional[SecretResolver] = None,
    redact: bool = True,
) -> SecretResolution:
    """Resolve a credential input to a :class:`SecretResolution`.

    Backward compatible: a plain string is returned verbatim (with the existing
    ``${ENV}`` convention honoured), so plaintext configs keep working. A
    :class:`SecretRef` (or its ``{"source", "id"}`` dict form) is resolved via
    the matching resolver. A resolved value is registered for log redaction
    unless ``redact=False``.
    """
    ref = _coerce_ref(value)
    if ref is None:
        # Plain string path — honour ${ENV} but otherwise use verbatim.
        text = value if isinstance(value, str) else ""
        if text.startswith("${") and text.endswith("}"):
            env_key = text[2:-1]
            raw = os.environ.get(env_key, "")
            if not raw:
                return SecretResolution(MISSING, detail=f"env var {env_key!r} not set")
            if redact:
                register_secret_for_redaction(raw)
            return SecretResolution(AVAILABLE, value=raw)
        if redact and text:
            register_secret_for_redaction(text)
        return SecretResolution(AVAILABLE if text else MISSING, value=text or None)

    result = (resolver or _pick_resolver(ref)).resolve(ref)
    if result.available and result.value and redact:
        register_secret_for_redaction(result.value)
    return result


def is_secret_ref(value: object) -> bool:
    """True if ``value`` is a :class:`SecretRef` or its dict reference form."""
    return _coerce_ref(value) is not None


def _coerce_ref(value: object) -> Optional[SecretRef]:
    if isinstance(value, SecretRef):
        return value
    if isinstance(value, dict) and "source" in value and "id" in value:
        return SecretRef(
            source=str(value["source"]),
            id=str(value["id"]),
            provider=(str(value["provider"]) if value.get("provider") else None),
        )
    return None


# ────────────────────────────────────────────────────────────────────────────
# Redaction registry — resolved secret values scrubbed from logs / errors.
# ────────────────────────────────────────────────────────────────────────────

_redaction_values: set = set()
_redaction_lock = threading.Lock()
_REDACTED = "[REDACTED]"

# Never register trivially short values — they would over-redact ordinary text.
_MIN_REDACT_LEN = 4


def register_secret_for_redaction(value: str) -> None:
    """Register a resolved secret value so :func:`redact_secrets` masks it."""
    if not value or not isinstance(value, str) or len(value) < _MIN_REDACT_LEN:
        return
    with _redaction_lock:
        _redaction_values.add(value)


def redact_secrets(text: str) -> str:
    """Replace every registered secret value in ``text`` with ``[REDACTED]``."""
    if not text or not isinstance(text, str):
        return text
    with _redaction_lock:
        values = sorted(_redaction_values, key=len, reverse=True)
    for secret in values:
        if secret in text:
            text = text.replace(secret, _REDACTED)
    return text


# ────────────────────────────────────────────────────────────────────────────
# Outbound redaction — the safe-by-default reply-path primitive (Issue #5055).
#
# ``redact_secrets`` masks only values the framework has *seen* (resolved
# credentials). An unregistered secret surfaced in a tool result or a document
# would still slip through, so the outbound primitive additionally masks tokens
# by *shape* (API keys, bearer tokens, ``AKIA…``, private-key blocks). This is
# the counterpart to log redaction: it is applied to text on its way to a chat
# user, before dispatch, by the wrapper's delivery seam.
# ────────────────────────────────────────────────────────────────────────────

# Credential-shaped patterns, matched by value (not key=value), so a naked token
# echoed by the model or embedded in a tool result is caught even when never
# registered. Kept deliberately narrow to avoid over-redacting ordinary text.
_CREDENTIAL_SHAPE_PATTERNS = (
    # OpenAI-style keys (sk-..., sk-proj-...), Anthropic (sk-ant-...)
    r"\bsk-(?:ant-|proj-)?[A-Za-z0-9_-]{16,}\b",
    # AWS access key id
    r"\bAKIA[0-9A-Z]{16}\b",
    # GitHub tokens (ghp_, gho_, ghu_, ghs_, ghr_, github_pat_)
    r"\bgh[pousr]_[A-Za-z0-9]{16,}\b",
    r"\bgithub_pat_[A-Za-z0-9_]{22,}\b",
    # Google API key
    r"\bAIza[0-9A-Za-z_-]{35}\b",
    # Slack token
    r"\bxox[baprs]-[0-9A-Za-z-]{10,}\b",
    # Bearer token in an Authorization-style value
    r"\bBearer\s+[A-Za-z0-9._-]{16,}\b",
    # PEM private-key block
    r"-----BEGIN (?:RSA |EC |OPENSSH |DSA |PGP )?PRIVATE KEY-----"
    r"[\s\S]*?-----END (?:RSA |EC |OPENSSH |DSA |PGP )?PRIVATE KEY-----",
)

_credential_shape_re = None


def _get_credential_shape_re():
    """Compile the credential-shape matcher lazily (stdlib ``re`` only)."""
    global _credential_shape_re
    if _credential_shape_re is None:
        import re

        _credential_shape_re = re.compile(
            "|".join(f"(?:{p})" for p in _CREDENTIAL_SHAPE_PATTERNS)
        )
    return _credential_shape_re


def redact_outbound(text: str) -> str:
    """Scrub secrets from text on its way to a chat user (safe-by-default).

    Combines the registered-value registry (:func:`redact_secrets`, holding
    every resolved gateway credential) with a credential-shape regex so an
    *unregistered* token surfaced in a tool result is still masked. Personal
    data is intentionally out of scope here — an opt-in PII policy layers on top
    via the wrapper/plugin hook — so ordinary text is never over-redacted.

    Zero dependency, never raises: a scrubber error returns the registered-value
    result rather than blocking delivery.
    """
    if not text or not isinstance(text, str):
        return text
    text = redact_secrets(text)
    try:
        text = _get_credential_shape_re().sub(_REDACTED, text)
    except Exception:  # pragma: no cover — never block delivery on a regex bug
        pass
    return text


@runtime_checkable
class OutboundRedactor(Protocol):
    """Overridable contract for scrubbing outbound text before dispatch.

    The default implementation is :func:`redact_outbound`. A deployment may
    supply its own (e.g. one that also applies a PII policy) and inject it at
    the wrapper's delivery seam without importing anything heavy into core.
    """

    def redact(self, text: str) -> str: ...
