"""URL-borne secrets are redacted by redact_string (issue #5758)."""

from praisonaiagents.trace.redact import redact_string, scrub_pii_text


def test_userinfo_password_redacted():
    out = redact_string("postgres://admin:hunter2@db.internal:5432/app")
    assert "hunter2" not in out and "admin" not in out
    assert out == "postgres://[REDACTED]@db.internal:5432/app"


def test_userinfo_password_with_at_sign_fully_redacted():
    out = redact_string("connecting https://svc:p@ssword@mcp.example.com/sse")
    assert "ssword" not in out
    assert out == "connecting https://[REDACTED]@mcp.example.com/sse"


def test_userinfo_token_only_redacted():
    out = redact_string("cloning https://ghp_abc123@github.com/o/r.git")
    assert "ghp_abc123" not in out
    assert "github.com/o/r.git" in out


def test_bot_token_path_redacted():
    out = redact_string("POST https://api.telegram.org/bot123456:AAH-xY_z9/sendMessage")
    assert "AAH-xY_z9" not in out
    assert out.endswith("/bot[REDACTED]/sendMessage")


def test_sensitive_query_param_redacted():
    out = redact_string("https://mcp.example.com/sse?api_key=sk-secret")
    assert "sk-secret" not in out


def test_plain_urls_and_emails_untouched():
    url = "https://example.com/users/a@b?page=2"
    assert redact_string(url) == url
    assert scrub_pii_text("mail me@example.com") == "mail [REDACTED-EMAIL]"


def test_disabled_returns_unchanged():
    url = "https://u:p@host/"
    assert redact_string(url, enabled=False) == url
