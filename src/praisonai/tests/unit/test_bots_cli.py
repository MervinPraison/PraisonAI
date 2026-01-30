"""
Unit tests for bot CLI capabilities wiring.

Tests that BotCapabilities are correctly passed to Agent constructor.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock


class TestBotCapabilitiesWiring:
    """Test that bot capabilities are wired to Agent constructor."""
    
    def test_get_agent_kwargs_memory(self):
        """Test that --memory flag is converted to Agent kwargs."""
        from praisonai.cli.features.bots_cli import BotHandler, BotCapabilities
        
        handler = BotHandler()
        capabilities = BotCapabilities(memory=True)
        
        kwargs = handler._get_agent_kwargs(capabilities)
        
        assert kwargs.get("memory") is True
    
    def test_get_agent_kwargs_knowledge(self):
        """Test that --knowledge flag with sources is converted to Agent kwargs."""
        from praisonai.cli.features.bots_cli import BotHandler, BotCapabilities
        
        handler = BotHandler()
        capabilities = BotCapabilities(
            knowledge=True,
            knowledge_sources=["docs.pdf", "data.txt"]
        )
        
        kwargs = handler._get_agent_kwargs(capabilities)
        
        assert kwargs.get("knowledge") == ["docs.pdf", "data.txt"]
    
    def test_get_agent_kwargs_knowledge_no_sources(self):
        """Test that --knowledge flag without sources sets knowledge=True."""
        from praisonai.cli.features.bots_cli import BotHandler, BotCapabilities
        
        handler = BotHandler()
        capabilities = BotCapabilities(knowledge=True)
        
        kwargs = handler._get_agent_kwargs(capabilities)
        
        assert kwargs.get("knowledge") is True
    
    def test_get_agent_kwargs_skills(self):
        """Test that --skills flag is converted to Agent kwargs."""
        from praisonai.cli.features.bots_cli import BotHandler, BotCapabilities
        
        handler = BotHandler()
        capabilities = BotCapabilities(skills=["web_search", "code_exec"])
        
        kwargs = handler._get_agent_kwargs(capabilities)
        
        assert kwargs.get("skills") == ["web_search", "code_exec"]
    
    def test_get_agent_kwargs_thinking_medium(self):
        """Test that --thinking medium enables reflection."""
        from praisonai.cli.features.bots_cli import BotHandler, BotCapabilities
        
        handler = BotHandler()
        capabilities = BotCapabilities(thinking="medium")
        
        kwargs = handler._get_agent_kwargs(capabilities)
        
        assert kwargs.get("reflection") is True
    
    def test_get_agent_kwargs_thinking_high(self):
        """Test that --thinking high enables reflection."""
        from praisonai.cli.features.bots_cli import BotHandler, BotCapabilities
        
        handler = BotHandler()
        capabilities = BotCapabilities(thinking="high")
        
        kwargs = handler._get_agent_kwargs(capabilities)
        
        assert kwargs.get("reflection") is True
    
    def test_get_agent_kwargs_thinking_low(self):
        """Test that --thinking low does NOT enable reflection."""
        from praisonai.cli.features.bots_cli import BotHandler, BotCapabilities
        
        handler = BotHandler()
        capabilities = BotCapabilities(thinking="low")
        
        kwargs = handler._get_agent_kwargs(capabilities)
        
        assert "reflection" not in kwargs
    
    def test_get_agent_kwargs_model(self):
        """Test that --model is converted to Agent kwargs."""
        from praisonai.cli.features.bots_cli import BotHandler, BotCapabilities
        
        handler = BotHandler()
        capabilities = BotCapabilities(model="gpt-4o")
        
        kwargs = handler._get_agent_kwargs(capabilities)
        
        assert kwargs.get("llm") == "gpt-4o"
    
    def test_get_agent_kwargs_empty_capabilities(self):
        """Test that empty capabilities returns empty kwargs."""
        from praisonai.cli.features.bots_cli import BotHandler, BotCapabilities
        
        handler = BotHandler()
        capabilities = BotCapabilities()
        
        kwargs = handler._get_agent_kwargs(capabilities)
        
        assert kwargs == {}
    
    def test_get_agent_kwargs_none_capabilities(self):
        """Test that None capabilities returns empty kwargs."""
        from praisonai.cli.features.bots_cli import BotHandler
        
        handler = BotHandler()
        
        kwargs = handler._get_agent_kwargs(None)
        
        assert kwargs == {}
    
    @patch('praisonaiagents.Agent')
    def test_load_agent_passes_capabilities(self, mock_agent_class):
        """Test that _load_agent passes capabilities to Agent constructor."""
        from praisonai.cli.features.bots_cli import BotHandler, BotCapabilities
        
        mock_agent = Mock()
        mock_agent_class.return_value = mock_agent
        
        handler = BotHandler()
        capabilities = BotCapabilities(
            memory=True,
            knowledge=True,
            knowledge_sources=["docs.pdf"],
            skills=["web_search"],
            thinking="medium",
            model="gpt-4o",
        )
        
        # Call _load_agent without a file (uses default agent)
        with patch.object(handler, '_build_tools', return_value=[]):
            _ = handler._load_agent(None, capabilities)
        
        # Verify Agent was called with the right kwargs
        call_kwargs = mock_agent_class.call_args[1]
        
        assert call_kwargs.get("memory") is True
        assert call_kwargs.get("knowledge") == ["docs.pdf"]
        assert call_kwargs.get("skills") == ["web_search"]
        assert call_kwargs.get("reflection") is True
        assert call_kwargs.get("llm") == "gpt-4o"


class TestBotCapabilitiesDataclass:
    """Test BotCapabilities dataclass."""
    
    def test_default_values(self):
        """Test default values are correct."""
        from praisonai.cli.features.bots_cli import BotCapabilities
        
        caps = BotCapabilities()
        
        assert caps.memory is False
        assert caps.knowledge is False
        assert caps.knowledge_sources == []
        assert caps.skills == []
        assert caps.thinking is None
        assert caps.model is None
        assert caps.sandbox is False
    
    def test_to_dict(self):
        """Test to_dict method."""
        from praisonai.cli.features.bots_cli import BotCapabilities
        
        caps = BotCapabilities(memory=True, model="gpt-4o")
        d = caps.to_dict()
        
        assert d["memory"] is True
        assert d["model"] == "gpt-4o"


class TestBuildCapabilitiesFromArgs:
    """Test _build_capabilities_from_args function."""
    
    def test_builds_from_args(self):
        """Test building capabilities from argparse namespace."""
        from praisonai.cli.features.bots_cli import _build_capabilities_from_args
        from argparse import Namespace
        
        args = Namespace(
            memory=True,
            knowledge=True,
            knowledge_sources=["docs.pdf"],
            skills=["web_search"],
            thinking="medium",
            model="gpt-4o",
            browser=False,
            browser_profile="default",
            browser_headless=False,
            tools=[],
            skills_dir=None,
            memory_provider="default",
            web_search=False,
            web_provider="duckduckgo",
            sandbox=False,
            exec_enabled=False,
            auto_approve=False,
            session_id=None,
            user_id=None,
        )
        
        caps = _build_capabilities_from_args(args)
        
        assert caps.memory is True
        assert caps.knowledge is True
        assert caps.knowledge_sources == ["docs.pdf"]
        assert caps.skills == ["web_search"]
        assert caps.thinking == "medium"
        assert caps.model == "gpt-4o"
