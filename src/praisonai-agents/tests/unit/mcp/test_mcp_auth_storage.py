"""
Unit tests for MCP auth storage module.

TDD approach: These tests define the expected behavior of mcp_auth_storage.py
"""
import pytest
import os


class TestMCPAuthStorage:
    """Tests for MCPAuthStorage class."""
    
    @pytest.fixture
    def temp_auth_file(self, tmp_path):
        """Create a temporary auth file path."""
        return tmp_path / "mcp-auth.json"
    
    @pytest.fixture
    def auth_storage(self, temp_auth_file):
        """Create an MCPAuthStorage instance with temp file."""
        from praisonaiagents.mcp.mcp_auth_storage import MCPAuthStorage
        return MCPAuthStorage(filepath=str(temp_auth_file))
    
    def test_init_creates_empty_storage(self, auth_storage, temp_auth_file):
        """Storage initializes without creating file until first write."""
        # File should not exist until we write something
        assert not temp_auth_file.exists() or temp_auth_file.read_text() == "{}"
    
    def test_get_nonexistent_entry_returns_none(self, auth_storage):
        """Getting a non-existent entry returns None."""
        result = auth_storage.get("nonexistent")
        assert result is None
    
    def test_set_and_get_tokens(self, auth_storage):
        """Can set and retrieve tokens for an MCP server."""
        tokens = {
            "access_token": "test_access_token",
            "refresh_token": "test_refresh_token",
            "expires_at": 1234567890,
            "scope": "read write"
        }
        
        auth_storage.set_tokens("github", tokens, server_url="https://api.github.com/mcp")
        
        entry = auth_storage.get("github")
        assert entry is not None
        assert entry["tokens"]["access_token"] == "test_access_token"
        assert entry["tokens"]["refresh_token"] == "test_refresh_token"
        assert entry["server_url"] == "https://api.github.com/mcp"
    
    def test_set_and_get_client_info(self, auth_storage):
        """Can set and retrieve client info for dynamic registration."""
        client_info = {
            "client_id": "test_client_id",
            "client_secret": "test_client_secret",
            "client_id_issued_at": 1234567890,
            "client_secret_expires_at": 1234567890 + 3600
        }
        
        auth_storage.set_client_info("github", client_info, server_url="https://api.github.com/mcp")
        
        entry = auth_storage.get("github")
        assert entry is not None
        assert entry["client_info"]["client_id"] == "test_client_id"
    
    def test_get_for_url_validates_url(self, auth_storage):
        """get_for_url returns None if URL has changed."""
        tokens = {"access_token": "test"}
        auth_storage.set_tokens("github", tokens, server_url="https://api.github.com/mcp")
        
        # Same URL should work
        entry = auth_storage.get_for_url("github", "https://api.github.com/mcp")
        assert entry is not None
        
        # Different URL should return None
        entry = auth_storage.get_for_url("github", "https://different.url/mcp")
        assert entry is None
    
    def test_remove_entry(self, auth_storage):
        """Can remove an entry."""
        tokens = {"access_token": "test"}
        auth_storage.set_tokens("github", tokens)
        
        auth_storage.remove("github")
        
        assert auth_storage.get("github") is None
    
    def test_set_code_verifier(self, auth_storage):
        """Can set and get code verifier for PKCE."""
        auth_storage.set_code_verifier("github", "test_verifier")
        
        entry = auth_storage.get("github")
        assert entry["code_verifier"] == "test_verifier"
    
    def test_clear_code_verifier(self, auth_storage):
        """Can clear code verifier after use."""
        auth_storage.set_code_verifier("github", "test_verifier")
        auth_storage.clear_code_verifier("github")
        
        entry = auth_storage.get("github")
        assert entry is not None
        assert "code_verifier" not in entry or entry.get("code_verifier") is None
    
    def test_set_oauth_state(self, auth_storage):
        """Can set and get OAuth state for CSRF protection."""
        auth_storage.set_oauth_state("github", "random_state_123")
        
        state = auth_storage.get_oauth_state("github")
        assert state == "random_state_123"
    
    def test_clear_oauth_state(self, auth_storage):
        """Can clear OAuth state after use."""
        auth_storage.set_oauth_state("github", "random_state_123")
        auth_storage.clear_oauth_state("github")
        
        state = auth_storage.get_oauth_state("github")
        assert state is None
    
    def test_is_token_expired_no_tokens(self, auth_storage):
        """is_token_expired returns None if no tokens exist."""
        result = auth_storage.is_token_expired("nonexistent")
        assert result is None
    
    def test_is_token_expired_no_expiry(self, auth_storage):
        """is_token_expired returns False if no expiry set."""
        tokens = {"access_token": "test"}
        auth_storage.set_tokens("github", tokens)
        
        result = auth_storage.is_token_expired("github")
        assert result is False
    
    def test_is_token_expired_not_expired(self, auth_storage):
        """is_token_expired returns False if token not expired."""
        import time
        tokens = {
            "access_token": "test",
            "expires_at": time.time() + 3600  # 1 hour from now
        }
        auth_storage.set_tokens("github", tokens)
        
        result = auth_storage.is_token_expired("github")
        assert result is False
    
    def test_is_token_expired_expired(self, auth_storage):
        """is_token_expired returns True if token expired."""
        import time
        tokens = {
            "access_token": "test",
            "expires_at": time.time() - 3600  # 1 hour ago
        }
        auth_storage.set_tokens("github", tokens)
        
        result = auth_storage.is_token_expired("github")
        assert result is True
    
    def test_file_permissions(self, auth_storage, temp_auth_file):
        """Auth file should have restricted permissions (0600)."""
        tokens = {"access_token": "test"}
        auth_storage.set_tokens("github", tokens)
        
        # Check file exists and has correct permissions
        assert temp_auth_file.exists()
        # On Unix, check permissions
        if os.name != 'nt':
            mode = temp_auth_file.stat().st_mode & 0o777
            assert mode == 0o600, f"Expected 0600, got {oct(mode)}"
    
    def test_all_returns_all_entries(self, auth_storage):
        """all() returns all stored entries."""
        auth_storage.set_tokens("github", {"access_token": "gh_token"})
        auth_storage.set_tokens("tavily", {"access_token": "tv_token"})
        
        all_entries = auth_storage.all()
        assert "github" in all_entries
        assert "tavily" in all_entries
        assert len(all_entries) == 2
    
    def test_persistence_across_instances(self, temp_auth_file):
        """Data persists across MCPAuthStorage instances."""
        from praisonaiagents.mcp.mcp_auth_storage import MCPAuthStorage
        
        # First instance writes data
        storage1 = MCPAuthStorage(filepath=str(temp_auth_file))
        storage1.set_tokens("github", {"access_token": "test_token"})
        
        # Second instance reads data
        storage2 = MCPAuthStorage(filepath=str(temp_auth_file))
        entry = storage2.get("github")
        
        assert entry is not None
        assert entry["tokens"]["access_token"] == "test_token"


class TestMCPAuthStorageDefaults:
    """Tests for default file path behavior."""
    
    def test_default_filepath(self):
        """Default filepath is in user's praison config directory."""
        from praisonaiagents.mcp.mcp_auth_storage import get_default_auth_filepath
        
        default_path = get_default_auth_filepath()
        assert "praison" in str(default_path).lower() or ".praison" in str(default_path)
        assert default_path.endswith("mcp-auth.json")
