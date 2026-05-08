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
    _is_expiring,
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


def test_is_expiring():
    """Test token expiry detection."""
    import time
    current_ms = int(time.time() * 1000)
    
    # Token expires in 30 seconds (should be considered expiring with default 60s skew)
    soon_expired = current_ms + 30_000
    assert _is_expiring(soon_expired) is True
    
    # Token expires in 2 minutes (should not be expiring)
    not_expired = current_ms + 120_000
    assert _is_expiring(not_expired) is False
    
    # No expiry time
    assert _is_expiring(0) is False
    assert _is_expiring(None) is False


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
    
    assert headers["anthropic-beta"] == "oauth-2025-04-20,interleaved-thinking-2025-05-14"
    assert headers["user-agent"] == "claude-cli/2.1.0 (external, cli)"
    assert headers["x-app"] == "cli"