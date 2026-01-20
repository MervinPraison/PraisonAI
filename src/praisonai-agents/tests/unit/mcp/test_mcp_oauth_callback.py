"""
Unit tests for MCP OAuth callback server module.

TDD approach: These tests define the expected behavior of mcp_oauth_callback.py
"""
import pytest
import asyncio
import threading
import time


class TestOAuthCallbackServer:
    """Tests for OAuth callback server."""
    
    def test_default_port(self):
        """Default callback port is 19876 (same as OpenCode for consistency)."""
        from praisonaiagents.mcp.mcp_oauth_callback import OAUTH_CALLBACK_PORT
        assert OAUTH_CALLBACK_PORT == 19876
    
    def test_default_path(self):
        """Default callback path is /mcp/oauth/callback."""
        from praisonaiagents.mcp.mcp_oauth_callback import OAUTH_CALLBACK_PATH
        assert OAUTH_CALLBACK_PATH == "/mcp/oauth/callback"
    
    def test_get_redirect_url(self):
        """get_redirect_url returns the full callback URL."""
        from praisonaiagents.mcp.mcp_oauth_callback import get_redirect_url
        
        url = get_redirect_url()
        assert url == "http://127.0.0.1:19876/mcp/oauth/callback"
    
    def test_get_redirect_url_custom_port(self):
        """get_redirect_url supports custom port."""
        from praisonaiagents.mcp.mcp_oauth_callback import get_redirect_url
        
        url = get_redirect_url(port=8080)
        assert url == "http://127.0.0.1:8080/mcp/oauth/callback"


class TestOAuthCallbackHandler:
    """Tests for OAuthCallbackHandler class."""
    
    @pytest.fixture
    def handler(self):
        """Create an OAuthCallbackHandler instance."""
        from praisonaiagents.mcp.mcp_oauth_callback import OAuthCallbackHandler
        return OAuthCallbackHandler()
    
    def test_wait_for_callback_timeout(self, handler):
        """wait_for_callback raises TimeoutError if no callback received."""
        with pytest.raises(TimeoutError):
            handler.wait_for_callback("test_state", timeout=0.1)
    
    def test_receive_callback_sets_code(self, handler):
        """receive_callback stores the authorization code."""
        handler.receive_callback("test_state", "auth_code_123")
        
        # Should be able to get the code now
        code = handler.get_code("test_state")
        assert code == "auth_code_123"
    
    def test_wait_for_callback_returns_code(self, handler):
        """wait_for_callback returns code when received."""
        # Simulate callback in a separate thread
        def send_callback():
            time.sleep(0.05)
            handler.receive_callback("test_state", "auth_code_456")
        
        thread = threading.Thread(target=send_callback)
        thread.start()
        
        code = handler.wait_for_callback("test_state", timeout=1.0)
        assert code == "auth_code_456"
        
        thread.join()
    
    def test_state_mismatch_returns_none_for_wrong_state(self, handler):
        """get_code with wrong state returns None."""
        handler.receive_callback("state_a", "auth_code")
        
        # Getting code for wrong state returns None
        code = handler.get_code("state_b")
        assert code is None
        
        # Getting code for correct state works
        code = handler.get_code("state_a")
        assert code == "auth_code"
    
    def test_clear_state(self, handler):
        """clear_state removes pending callback data."""
        handler.receive_callback("test_state", "auth_code")
        handler.clear_state("test_state")
        
        # Should not find the code anymore
        code = handler.get_code("test_state")
        assert code is None


class TestOAuthCallbackServerAsync:
    """Tests for async callback server functionality."""
    
    @pytest.fixture
    def callback_handler(self):
        """Create an OAuthCallbackHandler instance."""
        from praisonaiagents.mcp.mcp_oauth_callback import OAuthCallbackHandler
        return OAuthCallbackHandler()
    
    @pytest.mark.asyncio
    async def test_async_wait_for_callback_timeout(self, callback_handler):
        """async_wait_for_callback raises TimeoutError if no callback."""
        with pytest.raises(asyncio.TimeoutError):
            await callback_handler.async_wait_for_callback("test_state", timeout=0.1)
    
    @pytest.mark.asyncio
    async def test_async_wait_for_callback_returns_code(self, callback_handler):
        """async_wait_for_callback returns code when received."""
        async def send_callback():
            await asyncio.sleep(0.05)
            callback_handler.receive_callback("test_state", "async_code_789")
        
        # Start callback sender
        task = asyncio.create_task(send_callback())
        
        code = await callback_handler.async_wait_for_callback("test_state", timeout=1.0)
        assert code == "async_code_789"
        
        await task


class TestGenerateState:
    """Tests for OAuth state generation."""
    
    def test_generate_state_returns_string(self):
        """generate_state returns a random string."""
        from praisonaiagents.mcp.mcp_oauth_callback import generate_state
        
        state = generate_state()
        assert isinstance(state, str)
        assert len(state) > 0
    
    def test_generate_state_is_unique(self):
        """generate_state returns unique values."""
        from praisonaiagents.mcp.mcp_oauth_callback import generate_state
        
        states = [generate_state() for _ in range(100)]
        assert len(set(states)) == 100  # All unique


class TestGenerateCodeVerifier:
    """Tests for PKCE code verifier generation."""
    
    def test_generate_code_verifier_returns_string(self):
        """generate_code_verifier returns a string."""
        from praisonaiagents.mcp.mcp_oauth_callback import generate_code_verifier
        
        verifier = generate_code_verifier()
        assert isinstance(verifier, str)
        assert len(verifier) >= 43  # PKCE spec minimum
        assert len(verifier) <= 128  # PKCE spec maximum
    
    def test_generate_code_verifier_is_url_safe(self):
        """generate_code_verifier uses URL-safe characters."""
        from praisonaiagents.mcp.mcp_oauth_callback import generate_code_verifier
        import re
        
        verifier = generate_code_verifier()
        # PKCE allows: [A-Z] / [a-z] / [0-9] / "-" / "." / "_" / "~"
        assert re.match(r'^[A-Za-z0-9\-._~]+$', verifier)


class TestGenerateCodeChallenge:
    """Tests for PKCE code challenge generation."""
    
    def test_generate_code_challenge_returns_string(self):
        """generate_code_challenge returns a string."""
        from praisonaiagents.mcp.mcp_oauth_callback import generate_code_challenge
        
        challenge = generate_code_challenge("test_verifier")
        assert isinstance(challenge, str)
        assert len(challenge) > 0
    
    def test_generate_code_challenge_is_deterministic(self):
        """Same verifier produces same challenge."""
        from praisonaiagents.mcp.mcp_oauth_callback import generate_code_challenge
        
        verifier = "test_verifier_12345"
        challenge1 = generate_code_challenge(verifier)
        challenge2 = generate_code_challenge(verifier)
        assert challenge1 == challenge2
    
    def test_generate_code_challenge_is_base64url(self):
        """Code challenge is base64url encoded (no padding)."""
        from praisonaiagents.mcp.mcp_oauth_callback import generate_code_challenge
        import re
        
        challenge = generate_code_challenge("test_verifier")
        # Base64url: [A-Z] / [a-z] / [0-9] / "-" / "_" (no padding =)
        assert re.match(r'^[A-Za-z0-9\-_]+$', challenge)
        assert '=' not in challenge
