"""Unit tests for security advisory hardening."""
from __future__ import annotations

import pytest


def test_webhook_fail_closed_without_secret(monkeypatch):
    from praisonai.bots.webhook_security import webhooks_require_verification

    monkeypatch.delenv("PRAISONAI_INSECURE_WEBHOOKS", raising=False)
    assert webhooks_require_verification() is True


def test_webhook_insecure_override(monkeypatch):
    from praisonai.bots.webhook_security import webhooks_require_verification

    monkeypatch.setenv("PRAISONAI_INSECURE_WEBHOOKS", "true")
    assert webhooks_require_verification() is False


def test_verify_hmac_valid_and_invalid():
    import hashlib
    import hmac

    from praisonai.bots.webhook_security import verify_hmac

    secret = "s3cret"
    body = b"payload"
    sig = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()

    assert verify_hmac(secret, body, sig) is True
    assert verify_hmac(secret, body, "deadbeef") is False
    assert verify_hmac(secret, body, None) is False
    assert verify_hmac("", body, sig) is False


def test_verify_hmac_prefix_and_algo():
    import hashlib
    import hmac

    from praisonai.bots.webhook_security import verify_hmac

    secret = "s3cret"
    body = b"payload"
    digest = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()

    assert verify_hmac(secret, body, f"sha256={digest}", prefix="sha256=") is True
    assert verify_hmac(secret, body, f"sha256={digest}") is True


def test_verify_hmac_unknown_digest_fails_closed():
    from praisonai.bots.webhook_security import verify_hmac

    assert verify_hmac("s3cret", b"payload", "deadbeef", digest="not-a-real-algo") is False


def test_hmac_webhook_verifier_case_insensitive_header():
    import hashlib
    import hmac

    from praisonai.bots.webhook_security import HmacWebhookVerifier

    secret = "s3cret"
    body = b"payload"
    sig = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()

    verifier = HmacWebhookVerifier(
        secret, signature_headers=["X-Hub-Signature-256"], prefix="sha256="
    )
    assert verifier.verify(
        headers={"x-hub-signature-256": sig}, raw_body=body
    ) is True
    assert verifier.verify(headers={"x-hub-signature-256": "bad"}, raw_body=body) is False


def test_enforce_webhook_verification_gate(monkeypatch):
    from praisonai.bots.webhook_security import (
        HmacWebhookVerifier,
        enforce_webhook_verification,
    )

    monkeypatch.delenv("PRAISONAI_INSECURE_WEBHOOKS", raising=False)

    assert enforce_webhook_verification(
        accepts_webhooks=False, verifier=None, headers={}, raw_body=b""
    ) is True

    assert enforce_webhook_verification(
        accepts_webhooks=True, verifier=None, headers={}, raw_body=b""
    ) is False

    monkeypatch.setenv("PRAISONAI_INSECURE_WEBHOOKS", "true")
    assert enforce_webhook_verification(
        accepts_webhooks=True, verifier=None, headers={}, raw_body=b""
    ) is True
    monkeypatch.delenv("PRAISONAI_INSECURE_WEBHOOKS", raising=False)

    import hashlib
    import hmac

    secret = "s3cret"
    body = b"payload"
    sig = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    verifier = HmacWebhookVerifier(secret, signature_headers=["X-Signature"])
    assert enforce_webhook_verification(
        accepts_webhooks=True,
        verifier=verifier,
        headers={"X-Signature": sig},
        raw_body=body,
    ) is True


def test_webhook_verifier_protocol_and_capabilities_roundtrip():
    from praisonaiagents.bots import (
        PlatformCapabilities,
        WebhookVerifierProtocol,
    )

    assert WebhookVerifierProtocol is not None

    caps = PlatformCapabilities(accepts_webhooks=True, verifies_webhook_signature=True)
    restored = PlatformCapabilities.from_dict(caps.to_dict())
    assert restored.accepts_webhooks is True
    assert restored.verifies_webhook_signature is True


def test_jobs_agent_root_rejects_escape(tmp_path, monkeypatch):
    from praisonai.jobs.path_validation import validate_agent_file_path

    root = tmp_path / "agents"
    root.mkdir()
    outside = tmp_path / "outside.yaml"
    outside.write_text("agents: []")
    monkeypatch.setenv("PRAISONAI_JOBS_AGENT_ROOT", str(root))

    with pytest.raises(ValueError, match="PRAISONAI_JOBS_AGENT_ROOT"):
        validate_agent_file_path(str(outside))


def test_jobs_agent_root_allows_inside(tmp_path, monkeypatch):
    from praisonai.jobs.path_validation import validate_agent_file_path

    root = tmp_path / "agents"
    root.mkdir()
    inside = root / "team.yaml"
    inside.write_text("agents: []")
    monkeypatch.setenv("PRAISONAI_JOBS_AGENT_ROOT", str(root))

    assert validate_agent_file_path(str(inside)) == str(inside)


def test_yaml_approve_blocks_critical_tools():
    from praisonaiagents.approval.registry import ApprovalRegistry

    registry = ApprovalRegistry()
    token = registry.set_yaml_approved_tools(["execute_code", "search_web"])
    try:
        assert registry.is_yaml_approved("search_web") is True
        assert registry.is_yaml_approved("execute_code") is False
    finally:
        registry.reset_yaml_approved_tools(token)


def test_sandbox_blocks_format():
    from praisonaiagents.tools.python_tools import _validate_code_ast

    assert _validate_code_ast('"{0.__class__}".format(42)') is not None
    assert _validate_code_ast('"".format_map({})') is not None


def test_sse_security_middleware_rejects_bad_origin(monkeypatch):
    import asyncio

    from starlette.applications import Starlette
    from starlette.responses import PlainTextResponse
    from starlette.routing import Route

    from praisonaiagents.mcp.mcp_security import SecurityConfig, build_sse_security_app

    monkeypatch.delenv("MCP_SSE_ALLOWED_ORIGINS", raising=False)
    monkeypatch.delenv("MCP_SSE_AUTH_TOKEN", raising=False)
    monkeypatch.delenv("MCP_AUTH_TOKEN", raising=False)

    app = Starlette(routes=[Route("/", lambda r: PlainTextResponse("ok"))])
    config = SecurityConfig(validate_origin=True, allowed_origins=["localhost"])
    app = build_sse_security_app(app, config)

    async def _run(origin: str):
        scope = {
            "type": "http",
            "method": "GET",
            "path": "/",
            "headers": [(b"origin", origin.encode())],
        }
        status_code = 500

        async def receive():
            return {"type": "http.request", "body": b"", "more_body": False}

        async def send(message):
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]

        await app(scope, receive, send)
        return status_code

    assert asyncio.run(_run("https://evil.com")) == 403
    assert asyncio.run(_run("http://localhost:8080")) == 200
