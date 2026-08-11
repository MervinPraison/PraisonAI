"""Tests for Claude Code subscription auth."""
import os
import sys
import json
import tempfile
import pytest
from unittest.mock import patch, mock_open
from pathlib import Path

from praisonaiagents.auth.subscription.claude_code import (
    ClaudeCodeAuth,
    _read_keychain_credentials,
    _read_file_credentials,
    AuthError
)


def test_keychain_path_returns_none_off_darwin():
    """Test keychain reading returns None on non-macOS platforms."""
    with patch.object(sys, 'platform', 'linux'):
        assert _read_keychain_credentials() is None


def test_file_path_reads_credentials(monkeypatch):
    """Test file credential reading."""
    # Create a temporary file with Claude Code credentials
    credentials_data = {
        "claudeAiOauth": {
            "accessToken": "sk-ant-oat-test",
            "refreshToken": "rt-test",
            "expiresAt": 9999999999000,
        }
    }
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as tmp:
        json.dump(credentials_data, tmp)
        tmp_path = tmp.name
    
    try:
        with patch('praisonaiagents.auth.subscription.claude_code.Path') as mock_path:
            mock_home_path = mock_path.home.return_value
            mock_claude_path = mock_home_path / ".claude" / ".credentials.json"
            mock_claude_path.exists.return_value = True
            mock_claude_path.read_text.return_value = json.dumps(credentials_data)
            
            creds = _read_file_credentials()
            assert creds["accessToken"] == "sk-ant-oat-test"
            assert creds["refreshToken"] == "rt-test"
            assert creds["source"] == "claude-code-file"
    finally:
        os.unlink(tmp_path)


def test_refresh_is_read_only():
    """Refresh must not rotate shared Keychain OAuth tokens."""
    auth = ClaudeCodeAuth()
    with pytest.raises(AuthError, match="does not refresh shared Claude Code"):
        auth.refresh()


def test_resolve_credentials_does_not_refresh_when_expiring(monkeypatch):
    """Expiring tokens are returned as-is; no network refresh."""
    import time
    # Isolate from ambient OAuth env vars so the Keychain path is exercised.
    monkeypatch.delenv("ANTHROPIC_TOKEN", raising=False)
    monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)
    monkeypatch.setattr(
        "praisonaiagents.auth.subscription.claude_code._read_keychain_credentials",
        lambda: {
            "accessToken": "sk-ant-oat-test",
            "refreshToken": "rt-test",
            "expiresAt": int(time.time() * 1000) + 5_000,
            "source": "claude-code-keychain",
        },
    )

    auth = ClaudeCodeAuth()
    creds = auth.resolve_credentials()
    assert creds.api_key == "sk-ant-oat-test"
    assert creds.source == "claude-code-keychain"


def test_resolve_credentials_uses_env_first(monkeypatch):
    """Test that environment variables take precedence."""
    monkeypatch.setenv("ANTHROPIC_TOKEN", "sk-ant-oat-from-env")
    
    auth = ClaudeCodeAuth()
    creds = auth.resolve_credentials()
    
    assert creds.api_key == "sk-ant-oat-from-env"
    assert creds.base_url == "https://api.anthropic.com"
    assert creds.headers["x-app"] == "cli"
    assert creds.headers["user-agent"].startswith("claude-cli/")
    assert creds.source == "env:ANTHROPIC_TOKEN"


def test_resolve_credentials_no_auth_raises_error():
    """Test that missing credentials raises AuthError."""
    auth = ClaudeCodeAuth()
    
    with patch.dict(os.environ, {}, clear=True):
        with patch('praisonaiagents.auth.subscription.claude_code._read_keychain_credentials', return_value=None):
            with patch('praisonaiagents.auth.subscription.claude_code._read_file_credentials', return_value=None):
                with pytest.raises(AuthError) as exc_info:
                    auth.resolve_credentials()
                
                assert "No Claude Code credentials found" in str(exc_info.value)


def test_headers_for_includes_required_oauth_headers():
    """Test that OAuth-specific headers are included."""
    auth = ClaudeCodeAuth()
    headers = auth.headers_for("https://api.anthropic.com", "claude-3-haiku")

    assert "interleaved-thinking-2025-05-14" in headers["anthropic-beta"]
    assert "fine-grained-tool-streaming-2025-05-14" in headers["anthropic-beta"]
    assert "claude-code-20250219" in headers["anthropic-beta"]
    # The unsupported long-context beta caused subscription API failures and
    # must stay removed for shared OAuth sessions.
    assert "context-1m-2025-08-07" not in headers["anthropic-beta"]
    assert headers["user-agent"].startswith("claude-cli/")
    assert headers["x-app"] == "cli"