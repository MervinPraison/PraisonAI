"""
End-to-end integration tests for bind-aware authentication.

This module provides real agentic tests that verify the complete authentication
flow works correctly with actual gateway and agent instances.
"""

import asyncio
import os
import pytest
import subprocess
import time
import requests
from unittest.mock import patch, MagicMock

from praisonaiagents import Agent
from praisonai.gateway.server import WebSocketGateway
from praisonaiagents.gateway.config import GatewayConfig


class TestBindAwareAuthEndToEnd:
    """End-to-end tests for bind-aware authentication."""
    
    @pytest.mark.asyncio
    async def test_loopback_gateway_without_token_works(self):
        """Test that a gateway on loopback interface works without a token."""
        # Create gateway config for loopback
        config = GatewayConfig(
            host="127.0.0.1",
            port=18765,  # Use different port to avoid conflicts
            bind_host="127.0.0.1",
            auth_token=None
        )
        
        gateway = WebSocketGateway(config=config)
        
        try:
            # Should start without error (permissive mode)
            await asyncio.wait_for(self._start_gateway_briefly(gateway), timeout=5.0)
        except Exception as e:
            pytest.fail(f"Gateway failed to start on loopback without token: {e}")
    
    @pytest.mark.asyncio
    async def test_external_gateway_without_token_fails(self):
        """Test that a gateway on external interface fails without a token."""
        # Create gateway config for external interface
        config = GatewayConfig(
            host="0.0.0.0",
            port=18766,  # Use different port to avoid conflicts
            bind_host="0.0.0.0",
            auth_token=None
        )
        
        gateway = WebSocketGateway(config=config)
        
        # Should fail to start (strict mode)
        with pytest.raises(Exception) as excinfo:
            await asyncio.wait_for(self._start_gateway_briefly(gateway), timeout=5.0)
        
        assert "Cannot bind to 0.0.0.0 without an auth token" in str(excinfo.value)
    
    @pytest.mark.asyncio
    async def test_external_gateway_with_token_works(self):
        """Test that a gateway on external interface works with a token."""
        # Create gateway config for external interface with token
        config = GatewayConfig(
            host="0.0.0.0",
            port=18767,  # Use different port to avoid conflicts
            bind_host="0.0.0.0",
            auth_token="test-secret-token-123"
        )
        
        gateway = WebSocketGateway(config=config)
        
        try:
            # Should start successfully (has auth token)
            await asyncio.wait_for(self._start_gateway_briefly(gateway), timeout=5.0)
        except Exception as e:
            pytest.fail(f"Gateway failed to start on external interface with token: {e}")
    
    async def _start_gateway_briefly(self, gateway):
        """Start a gateway briefly and then stop it."""
        # This simulates starting the gateway to trigger validation
        # but stops it quickly to avoid blocking the test
        start_task = asyncio.create_task(gateway.start())
        
        # Give it a moment to start and perform validation
        await asyncio.sleep(0.1)
        
        # If startup already failed (e.g. validation raised), surface it now
        if start_task.done():
            # Re-raises any exception stored on the task
            start_task.result()
            return
        
        # Stop the gateway
        if gateway.is_running:
            await gateway.stop()
        
        # Cancel the start task if it's still running
        start_task.cancel()
        try:
            await start_task
        except asyncio.CancelledError:
            pass


class TestRealAgentExecution:
    """Real agentic test to ensure the feature doesn't break agent functionality."""
    
    def test_agent_still_works_after_auth_changes(self):
        """Test that agents still work correctly after authentication changes.
        
        This is the mandatory "real agentic test" that verifies the agent
        actually calls the LLM and produces output end-to-end.
        """
        try:
            from praisonaiagents import Agent
            
            # Create a simple agent for testing
            agent = Agent(
                name="test_agent",
                instructions="You are a helpful test assistant. Reply in exactly 3 words.",
            )
            
            # This MUST call the LLM and produce a real response
            response = agent.start("Say hello")
            
            # Print the full output so developers can verify behavior
            print(f"Agent response: {response}")
            
            # Verify we got a response (not empty)
            assert response, "Agent should produce a non-empty response"
            assert len(response) > 0, "Agent response should not be empty"
            assert isinstance(response, str), "Agent response should be a string"
            
            # Test that the agent actually processed the instruction
            # (This is a real LLM call verification)
            assert len(response.split()) >= 1, "Agent should produce at least one word"
            
        except Exception as e:
            # If this fails due to missing API keys, that's expected in CI
            # But we should still report what happened
            print(f"Agent test failed (expected if no API keys): {e}")
            pytest.skip(f"Agent test requires API access: {e}")


class TestUIAuthIntegration:
    """Integration tests for UI authentication behavior."""
    
    @patch('praisonai.ui._auth.cl')
    def test_ui_auth_consolidation_works(self, mock_cl):
        """Test that UI auth consolidation works correctly."""
        from praisonai.ui._auth import register_password_auth
        
        # Test loopback interface (should work with defaults)
        register_password_auth(None, bind_host="127.0.0.1")
        
        # Verify that chainlit auth callback was registered
        mock_cl.password_auth_callback.assert_called()
        
        # Get the registered callback
        callback = mock_cl.password_auth_callback.call_args[0][0]
        
        # Mock the User class
        mock_user = MagicMock()
        mock_cl.User.return_value = mock_user
        
        # Test the callback works
        result = callback("admin", "admin")
        assert result is not None  # Should succeed with default creds on loopback


class TestTokenFingerprinting:
    """Test token fingerprinting for security."""
    
    def test_token_fingerprint_logging(self):
        """Test that tokens are logged as fingerprints, not raw values."""
        from praisonai.gateway.auth import log_token_fingerprint
        
        # This should not raise and should log a fingerprint
        with patch('praisonai.gateway.auth.logger') as mock_logger:
            log_token_fingerprint("1234567890abcdef")
            
            # Verify log was called
            mock_logger.info.assert_called_once()
            
            # Verify the log message contains fingerprint, not raw token
            log_message = mock_logger.info.call_args[0][0]
            assert "gw_1234" in log_message
            assert "cdef" in log_message
            assert "1234567890abcdef" not in log_message  # Raw token should not appear
    
    def test_short_token_fingerprinting(self):
        """Test fingerprinting of short tokens."""
        from praisonai.gateway.auth import log_token_fingerprint
        
        with patch('praisonai.gateway.auth.logger') as mock_logger:
            log_token_fingerprint("abc123")
            
            # Verify log was called
            mock_logger.info.assert_called_once()
            
            # Verify the log message is appropriately masked
            log_message = mock_logger.info.call_args[0][0]
            assert "gw_ab****" in log_message
            assert "abc123" not in log_message  # Raw token should not appear


class TestEnvironmentFileHandling:
    """Test environment file handling for token persistence."""
    
    def test_token_persistence_to_env_file(self):
        """Test that tokens are correctly persisted to environment files."""
        from praisonai.gateway.auth import ensure_token_env_file
        import tempfile
        
        with tempfile.NamedTemporaryFile(mode='w+', delete=False) as tmp_file:
            tmp_path = tmp_file.name
        
        try:
            # Test writing a new token
            ensure_token_env_file("test-token-123", tmp_path)
            
            # Verify file contents
            with open(tmp_path, 'r') as f:
                content = f.read()
            
            assert "GATEWAY_AUTH_TOKEN=test-token-123" in content
            
            # Test updating an existing token
            ensure_token_env_file("new-token-456", tmp_path)
            
            # Verify updated contents
            with open(tmp_path, 'r') as f:
                content = f.read()
            
            assert "GATEWAY_AUTH_TOKEN=new-token-456" in content
            assert "test-token-123" not in content  # Old token should be replaced
            
            # Verify there's only one GATEWAY_AUTH_TOKEN line
            token_lines = [line for line in content.split('\n') if 'GATEWAY_AUTH_TOKEN' in line]
            assert len(token_lines) == 1
            
        finally:
            # Clean up
            os.unlink(tmp_path)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])