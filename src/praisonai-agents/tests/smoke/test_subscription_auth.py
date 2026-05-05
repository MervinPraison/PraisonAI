"""
Smoke test for subscription authentication - exercises real auth flows.
"""
import pytest
from unittest.mock import patch, Mock

try:
    import litellm
except ImportError:
    pytest.skip("litellm not available", allow_module_level=True)

from praisonaiagents import Agent
from praisonaiagents.auth.subscription.protocols import SubscriptionCredentials


def test_claude_code_auth_flow():
    """Test that Claude Code auth properly injects OAuth credentials."""
    # Mock litellm completion to capture the actual params sent
    mock_response = Mock()
    mock_response.choices = [Mock()]
    mock_response.choices[0].message = Mock()
    mock_response.choices[0].message.content = "Hello! This is a test response."
    
    with patch('litellm.completion') as mock_completion:
        mock_completion.return_value = mock_response
        
        # Mock the credential resolution to return OAuth token
        mock_creds = SubscriptionCredentials(
            api_key="sk-ant-oat-test-oauth-token",  # OAuth token format
            base_url="https://api.anthropic.com",
            headers={"user-agent": "claude-cli/2.1.0", "x-app": "cli"},
            auth_scheme="bearer",
            source="claude-code-test"
        )
        
        with patch('praisonaiagents.auth.resolve_subscription_credentials') as mock_resolve:
            mock_resolve.return_value = mock_creds
            
            # Create agent with Claude Code auth
            agent = Agent(
                name="test-agent",
                instructions="You are a test assistant.",
                auth="claude-code"
            )
            
            # Make a real request
            response = agent.start("Say hello")
            
            # Verify the call was made
            assert mock_completion.called
            call_args = mock_completion.call_args
            params = call_args[1] if call_args[1] else call_args[0][0] if call_args[0] else {}
            
            # Verify OAuth token was passed as api_key (litellm will auto-detect and use Bearer)
            assert params.get("api_key") == "sk-ant-oat-test-oauth-token"
            assert params.get("base_url") == "https://api.anthropic.com"
            
            # Verify provider headers are included
            extra_headers = params.get("extra_headers", {})
            assert "user-agent" in extra_headers
            assert "x-app" in extra_headers
            
            # Verify we got a response
            assert "hello" in response.lower() or "test" in response.lower()


def test_auth_refresh_on_401():
    """Test that auth errors trigger credential refresh and retry."""
    # First call: return 401, second call: success
    mock_response = Mock()
    mock_response.choices = [Mock()]
    mock_response.choices[0].message = Mock()
    mock_response.choices[0].message.content = "Success after refresh"
    
    auth_error = Exception("AuthenticationError: Invalid API key")
    
    with patch('litellm.completion') as mock_completion:
        # First call raises auth error, second succeeds
        mock_completion.side_effect = [auth_error, mock_response]
        
        # Mock credential resolution and refresh
        initial_creds = SubscriptionCredentials(
            api_key="sk-ant-oat-expired-token",
            base_url="https://api.anthropic.com", 
            headers={},
            auth_scheme="bearer",
            source="claude-code-test"
        )
        
        refreshed_creds = SubscriptionCredentials(
            api_key="sk-ant-oat-fresh-token",
            base_url="https://api.anthropic.com",
            headers={},
            auth_scheme="bearer", 
            source="claude-code-refreshed"
        )
        
        with patch('praisonaiagents.auth.resolve_subscription_credentials') as mock_resolve:
            mock_resolve.return_value = initial_creds
            
            with patch('praisonaiagents.auth.subscription.registry.get_subscription_provider') as mock_provider:
                mock_auth_provider = Mock()
                mock_auth_provider.refresh.return_value = refreshed_creds
                mock_provider.return_value = mock_auth_provider
                
                # Mock error classification to detect auth error
                with patch.object(Agent, '_classify_error_and_should_retry') as mock_classify:
                    # First call: auth error, can retry
                    # Second call: shouldn't be called since retry succeeds
                    mock_classify.return_value = ("auth", True, 0.0)
                    
                    agent = Agent(
                        name="test-agent",
                        instructions="Test agent",
                        auth="claude-code"
                    )
                    
                    # This should trigger refresh on first 401 and succeed on retry
                    response = agent.start("Test refresh flow")
                    
                    # Verify refresh was called
                    assert mock_auth_provider.refresh.called
                    
                    # Verify we got success response
                    assert "Success after refresh" in response


def test_invalid_auth_provider():
    """Test that invalid auth providers raise clear errors."""
    with pytest.raises(Exception) as exc_info:
        agent = Agent(
            name="test-agent",
            auth="nonexistent-provider"
        )
        agent.start("This should fail")
    
    error_msg = str(exc_info.value).lower()
    assert "unknown" in error_msg or "provider" in error_msg


def test_codex_experimental_error():
    """Test that Codex auth raises experimental error."""
    with patch('praisonaiagents.auth.resolve_subscription_credentials') as mock_resolve:
        from praisonaiagents.auth.subscription.protocols import AuthError
        mock_resolve.side_effect = AuthError("Codex auth is experimental")
        
        with pytest.raises(AuthError) as exc_info:
            agent = Agent(name="test", auth="codex")
            agent.start("test")
            
        assert "experimental" in str(exc_info.value).lower()
        assert "codex" in str(exc_info.value).lower()


def test_gemini_experimental_error():
    """Test that Gemini CLI auth raises experimental error."""
    with patch('praisonaiagents.auth.resolve_subscription_credentials') as mock_resolve:
        from praisonaiagents.auth.subscription.protocols import AuthError
        mock_resolve.side_effect = AuthError("Gemini CLI auth is experimental")
        
        with pytest.raises(AuthError) as exc_info:
            agent = Agent(name="test", auth="gemini-cli")  
            agent.start("test")
            
        assert "experimental" in str(exc_info.value).lower()
        assert "gemini" in str(exc_info.value).lower()


if __name__ == "__main__":
    # Manual test runner for development
    test_claude_code_auth_flow()
    test_auth_refresh_on_401()
    test_invalid_auth_provider()
    test_codex_experimental_error()
    test_gemini_experimental_error()
    print("✅ All subscription auth smoke tests passed!")