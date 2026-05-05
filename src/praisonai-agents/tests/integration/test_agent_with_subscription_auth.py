"""Integration tests for Agent with subscription auth."""
import pytest
from unittest.mock import patch, MagicMock

from praisonaiagents import Agent
from praisonaiagents.auth.subscription.protocols import SubscriptionCredentials


@pytest.fixture
def mock_subscription_auth():
    """Mock subscription auth that returns test credentials."""
    def mock_resolve_credentials(provider_id):
        if provider_id == "claude-code":
            return SubscriptionCredentials(
                api_key="sk-ant-oat-stub",
                base_url="https://api.anthropic.com",
                headers={
                    "anthropic-beta": "oauth-2025-04-20,interleaved-thinking-2025-05-14",
                    "user-agent": "claude-cli/2.1.0 (external, cli)",
                    "x-app": "cli",
                },
                auth_scheme="bearer",
                source="test-mock"
            )
        else:
            raise Exception(f"Unknown provider: {provider_id}")
    
    return mock_resolve_credentials


def test_agent_accepts_auth_kwarg(mock_subscription_auth):
    """Test that Agent accepts auth parameter and passes it to LLM."""
    with patch('praisonaiagents.auth.resolve_subscription_credentials', mock_subscription_auth):
        agent = Agent(
            name="test-agent", 
            llm="anthropic/claude-3-haiku-20240307", 
            auth="claude-code"
        )
        
        assert hasattr(agent, 'llm_instance')
        assert agent.llm_instance._auth_provider_id == "claude-code"


def test_llm_kwargs_carry_oauth_headers(mock_subscription_auth):
    """Test that LLM completion params include OAuth headers."""
    with patch('praisonaiagents.auth.resolve_subscription_credentials', mock_subscription_auth):
        from praisonaiagents.llm import LLM
        
        llm = LLM(model="anthropic/claude-3-haiku-20240307", auth="claude-code")
        params = llm._build_completion_params()
        
        assert params["api_key"] == "sk-ant-oat-stub"
        assert params["base_url"] == "https://api.anthropic.com"
        assert params["extra_headers"]["x-app"] == "cli"
        assert params["extra_headers"]["user-agent"] == "claude-cli/2.1.0 (external, cli)"


def test_agent_without_auth_works_normally():
    """Test that Agent without auth parameter works as before."""
    agent = Agent(name="test-agent", llm="anthropic/claude-3-haiku-20240307")
    
    if hasattr(agent, 'llm_instance'):
        assert agent.llm_instance._auth_provider_id is None
        assert agent.llm_instance._cached_subscription_creds is None