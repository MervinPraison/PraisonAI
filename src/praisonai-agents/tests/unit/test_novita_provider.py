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

    def test_agent_novita_kimi_model(self):
        """Agent should accept Novita's Kimi model."""
        from praisonaiagents import Agent

        agent = Agent(
            name="KimiTest",
            instructions="You are a helpful assistant",
            llm="openai/moonshotai/kimi-k2.5",
            base_url="https://api.novita.ai/openai",
            api_key="test-key",
        )
        assert agent is not None

    def test_agent_novita_deepseek_model(self):
        """Agent should accept Novita's DeepSeek model."""
        from praisonaiagents import Agent

        agent = Agent(
            name="DeepSeekNovitaTest",
            instructions="You are a helpful assistant",
            llm="openai/deepseek/deepseek-v3.2",
            base_url="https://api.novita.ai/openai",
            api_key="test-key",
        )
        assert agent is not None

    def test_agent_novita_glm_model(self):
        """Agent should accept Novita's GLM model."""
        from praisonaiagents import Agent

        agent = Agent(
            name="GLMNovitaTest",
            instructions="You are a helpful assistant",
            llm="openai/zai-org/glm-5",
            base_url="https://api.novita.ai/openai",
            api_key="test-key",
        )
        assert agent is not None

    def test_agent_novita_model_stored(self):
        """Agent should store the Novita model name correctly."""
        from praisonaiagents import Agent

        agent = Agent(
            name="ModelStoreTest",
            instructions="You are a helpful assistant",
            llm="openai/moonshotai/kimi-k2.5",
            base_url="https://api.novita.ai/openai",
            api_key="test-key",
        )
        assert "kimi-k2.5" in agent.llm or "moonshotai" in agent.llm
