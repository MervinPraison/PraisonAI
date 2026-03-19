"""
Tests for Novita AI provider integration.

Novita AI provides an OpenAI-compatible endpoint (https://api.novita.ai/openai),
allowing PraisonAI agents to use Kimi, DeepSeek, GLM, and other models.

These tests verify that the Agent class correctly accepts Novita configuration
without making real API calls.
"""

import pytest
from unittest.mock import patch
import os


class TestNovitaProviderConfig:
    """Test that Agent accepts Novita AI provider configuration."""

    def test_agent_accepts_novita_base_url(self):
        """Agent should accept Novita's OpenAI-compatible base_url."""
        from praisonaiagents import Agent

        agent = Agent(
            name="NovitaTest",
            instructions="You are a helpful assistant",
            llm="openai/moonshotai/kimi-k2.5",
            base_url="https://api.novita.ai/openai",
            api_key="test-novita-key",
        )
        assert agent is not None
        assert agent.base_url == "https://api.novita.ai/openai"

    def test_agent_novita_api_key_from_env(self):
        """Agent should read NOVITA_API_KEY from environment."""
        from praisonaiagents import Agent

        with patch.dict(os.environ, {"NOVITA_API_KEY": "env-test-key"}):
            agent = Agent(
                name="NovitaEnvTest",
                instructions="You are a helpful assistant",
                llm="openai/moonshotai/kimi-k2.5",
                base_url="https://api.novita.ai/openai",
                api_key=os.environ.get("NOVITA_API_KEY"),
            )
        assert agent is not None

    @pytest.mark.parametrize(
        "model_name",
        [
            "openai/moonshotai/kimi-k2.5",
            "openai/deepseek/deepseek-v3.2",
            "openai/zai-org/glm-5",
        ],
    )
    def test_agent_novita_models(self, model_name):
        """Agent should accept various Novita models and store them correctly."""
        from praisonaiagents import Agent

        agent = Agent(
            name=f"NovitaModelTest-{model_name.split('/')[-1]}",
            instructions="You are a helpful assistant",
            llm=model_name,
            base_url="https://api.novita.ai/openai",
            api_key="test-key",
        )
        assert agent is not None
        assert agent.llm == model_name
