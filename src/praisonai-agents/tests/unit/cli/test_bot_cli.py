"""
Tests for bot CLI commands.

Tests the enhanced bot command with full capability options.

NOTE: These tests require the praisonai package to be installed.
They are skipped if praisonai is not available.
"""

import pytest
from unittest.mock import patch, MagicMock

# Skip entire module if praisonai is not installed
pytest.importorskip("praisonai", reason="praisonai package not installed")


class TestBotCapabilities:
    """Tests for BotCapabilities dataclass."""
    
    def test_bot_capabilities_defaults(self):
        """Test default values for BotCapabilities."""
        from praisonai.cli.features.bots_cli import BotCapabilities
        
        caps = BotCapabilities()
        
        assert caps.browser is False
        assert caps.browser_profile == "default"
        assert caps.browser_headless is False
        assert caps.tools == []
        assert caps.skills == []
        assert caps.memory is False
        assert caps.knowledge is False
        assert caps.web_search is False
        assert caps.sandbox is False
        assert caps.exec_enabled is False
        assert caps.model is None
        assert caps.auto_approve is False
    
    def test_bot_capabilities_custom_values(self):
        """Test custom values for BotCapabilities."""
        from praisonai.cli.features.bots_cli import BotCapabilities
        
        caps = BotCapabilities(
            browser=True,
            browser_profile="chrome",
            tools=["DuckDuckGoTool", "WikipediaTool"],
            memory=True,
            web_search=True,
            web_search_provider="tavily",
            model="gpt-4o",
        )
        
        assert caps.browser is True
        assert caps.browser_profile == "chrome"
        assert caps.tools == ["DuckDuckGoTool", "WikipediaTool"]
        assert caps.memory is True
        assert caps.web_search is True
        assert caps.web_search_provider == "tavily"
        assert caps.model == "gpt-4o"
    
    def test_bot_capabilities_to_dict(self):
        """Test to_dict method."""
        from praisonai.cli.features.bots_cli import BotCapabilities
        
        caps = BotCapabilities(browser=True, model="gpt-4o")
        result = caps.to_dict()
        
        assert isinstance(result, dict)
        assert result["browser"] is True
        assert result["model"] == "gpt-4o"
        assert "tools" in result
        assert "memory" in result


class TestBotHandler:
    """Tests for BotHandler class."""
    
    def test_bot_handler_init(self):
        """Test BotHandler initialization."""
        from praisonai.cli.features.bots_cli import BotHandler
        
        handler = BotHandler()
        assert handler is not None
    
    @patch('praisonai.cli.features.bots_cli.BotHandler._load_agent')
    def test_build_tools_browser(self, mock_load_agent):
        """Test _build_tools with browser enabled."""
        from praisonai.cli.features.bots_cli import BotHandler, BotCapabilities
        
        handler = BotHandler()
        caps = BotCapabilities(browser=True)
        
        # Mock the browser tool import
        with patch.dict('sys.modules', {'praisonai_tools': MagicMock()}):
            tools = handler._build_tools(caps)
            # Should attempt to add browser tool
            assert isinstance(tools, list)
    
    @patch('praisonai.cli.features.bots_cli.BotHandler._load_agent')
    def test_build_tools_web_search(self, mock_load_agent):
        """Test _build_tools with web search enabled."""
        from praisonai.cli.features.bots_cli import BotHandler, BotCapabilities
        
        handler = BotHandler()
        caps = BotCapabilities(web_search=True, web_search_provider="duckduckgo")
        
        with patch.dict('sys.modules', {'praisonai_tools': MagicMock()}):
            tools = handler._build_tools(caps)
            assert isinstance(tools, list)
    
    def test_resolve_tool_by_name_not_found(self):
        """Test _resolve_tool_by_name with non-existent tool."""
        from praisonai.cli.features.bots_cli import BotHandler
        
        handler = BotHandler()
        result = handler._resolve_tool_by_name("NonExistentTool12345")
        
        assert result is None
    
    def test_print_startup_info_no_capabilities(self, capsys):
        """Test _print_startup_info without capabilities."""
        from praisonai.cli.features.bots_cli import BotHandler
        
        handler = BotHandler()
        handler._print_startup_info("Telegram", None)
        
        captured = capsys.readouterr()
        assert "Starting Telegram bot" in captured.out
        assert "Press Ctrl+C to stop" in captured.out
    
    def test_print_startup_info_with_capabilities(self, capsys):
        """Test _print_startup_info with capabilities."""
        from praisonai.cli.features.bots_cli import BotHandler, BotCapabilities
        
        handler = BotHandler()
        caps = BotCapabilities(
            browser=True,
            memory=True,
            web_search=True,
        )
        handler._print_startup_info("Slack", caps)
        
        captured = capsys.readouterr()
        assert "Starting Slack bot" in captured.out
        assert "Capabilities:" in captured.out
        assert "browser" in captured.out
        assert "memory" in captured.out
    
class TestHandleBotCommand:
    """Tests for handle_bot_command function."""
    
    def test_handle_bot_command_no_platform(self, capsys):
        """Test handle_bot_command with no platform."""
        from praisonai.cli.features.bots_cli import handle_bot_command
        
        result = handle_bot_command([])
        
        assert result == 1
        captured = capsys.readouterr()
        assert "Available platforms" in captured.out
    
    def test_handle_bot_command_help_output(self, capsys):
        """Test handle_bot_command shows help."""
        from praisonai.cli.features.bots_cli import handle_bot_command
        
        handle_bot_command([])
        
        captured = capsys.readouterr()
        assert "telegram" in captured.out.lower()
        assert "discord" in captured.out.lower()
        assert "slack" in captured.out.lower()


class TestBuildCapabilitiesFromArgs:
    """Tests for _build_capabilities_from_args function."""
    
    def test_build_capabilities_from_args_defaults(self):
        """Test building capabilities from args with defaults."""
        from praisonai.cli.features.bots_cli import _build_capabilities_from_args
        
        class MockArgs:
            browser = False
            browser_profile = "default"
            browser_headless = False
            tools = []
            skills = []
            skills_dir = None
            memory = False
            memory_provider = "default"
            knowledge = False
            knowledge_sources = []
            web_search = False
            web_provider = "duckduckgo"
            sandbox = False
            exec_enabled = False
            model = None
            thinking = None
            session_id = None
            user_id = None
        
        caps = _build_capabilities_from_args(MockArgs())
        
        assert caps.browser is False
        assert caps.memory is False
        assert caps.web_search is False
    
    def test_build_capabilities_from_args_custom(self):
        """Test building capabilities from args with custom values."""
        from praisonai.cli.features.bots_cli import _build_capabilities_from_args
        
        class MockArgs:
            browser = True
            browser_profile = "chrome"
            browser_headless = True
            tools = ["DuckDuckGoTool"]
            skills = []
            skills_dir = None
            memory = True
            memory_provider = "redis"
            knowledge = False
            knowledge_sources = []
            web_search = True
            web_provider = "tavily"
            sandbox = False
            exec_enabled = False
            model = "gpt-4o"
            thinking = "medium"
            session_id = "test-session"
            user_id = "user-123"
        
        caps = _build_capabilities_from_args(MockArgs())
        
        assert caps.browser is True
        assert caps.browser_profile == "chrome"
        assert caps.tools == ["DuckDuckGoTool"]
        assert caps.memory is True
        assert caps.web_search is True
        assert caps.model == "gpt-4o"


class TestAddCapabilityArgs:
    """Tests for _add_capability_args function."""
    
    def test_add_capability_args(self):
        """Test that capability args are added to parser."""
        import argparse
        from praisonai.cli.features.bots_cli import _add_capability_args
        
        parser = argparse.ArgumentParser()
        _add_capability_args(parser)
        
        # Parse with defaults
        args = parser.parse_args([])
        
        assert hasattr(args, 'browser')
        assert hasattr(args, 'memory')
        assert hasattr(args, 'web_search')
        assert hasattr(args, 'tools')
        assert hasattr(args, 'model')
    
    def test_add_capability_args_with_values(self):
        """Test parsing capability args with values."""
        import argparse
        from praisonai.cli.features.bots_cli import _add_capability_args
        
        parser = argparse.ArgumentParser()
        _add_capability_args(parser)
        
        args = parser.parse_args([
            '--browser',
            '--memory',
            '--web',
            '--model', 'gpt-4o',
            '--tools', 'DuckDuckGoTool', 'WikipediaTool',
        ])
        
        assert args.browser is True
        assert args.memory is True
        assert args.web_search is True
        assert args.model == "gpt-4o"
        assert args.tools == ["DuckDuckGoTool", "WikipediaTool"]
    
