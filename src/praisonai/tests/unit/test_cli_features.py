"""
Unit tests for CLI features module.

Tests are organized by feature and use mocking to avoid actual API calls.
Each test is designed to run quickly (<1s) to maintain fast feedback loops.
"""

import pytest
import sys
import os
from unittest.mock import Mock, patch

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))


class TestGuardrailHandler:
    """Tests for --guardrail flag functionality."""
    
    def test_guardrail_handler_import(self):
        """Test that GuardrailHandler can be imported."""
        from praisonai.cli.features import GuardrailHandler
        assert GuardrailHandler is not None
    
    def test_guardrail_handler_initialization(self):
        """Test GuardrailHandler initialization."""
        from praisonai.cli.features.guardrail import GuardrailHandler
        handler = GuardrailHandler(verbose=True)
        assert handler.feature_name == "guardrail"
        assert handler.flag_name == "guardrail"
        assert handler.verbose is True
    
    def test_guardrail_check_dependencies_available(self):
        """Test dependency check when praisonaiagents is available."""
        from praisonai.cli.features.guardrail import GuardrailHandler
        handler = GuardrailHandler()
        available, msg = handler.check_dependencies()
        # Should be available if praisonaiagents is installed
        assert isinstance(available, bool)
        assert isinstance(msg, str)
    
    def test_guardrail_apply_to_agent_config(self):
        """Test applying guardrail to agent config."""
        from praisonai.cli.features.guardrail import GuardrailHandler
        handler = GuardrailHandler()
        config = {"name": "TestAgent"}
        result = handler.apply_to_agent_config(config, "Ensure output is valid JSON")
        assert "guardrail" in result or "guardrail_description" in result
    
    @patch('praisonai.cli.features.guardrail.PRAISONAI_AVAILABLE', True)
    def test_guardrail_execute_with_string(self):
        """Test executing guardrail with string description."""
        from praisonai.cli.features.guardrail import GuardrailHandler
        handler = GuardrailHandler()
        
        # Mock the LLMGuardrail
        with patch('praisonai.cli.features.guardrail.LLMGuardrail') as mock_guardrail:
            mock_instance = Mock()
            mock_instance.return_value = (True, "Valid output")
            mock_guardrail.return_value = mock_instance
            
            result = handler.execute(
                output="Test output",
                guardrail_description="Check if valid"
            )
            assert result is not None


class TestMetricsHandler:
    """Tests for --metrics flag functionality."""
    
    def test_metrics_handler_import(self):
        """Test that MetricsHandler can be imported."""
        from praisonai.cli.features import MetricsHandler
        assert MetricsHandler is not None
    
    def test_metrics_handler_initialization(self):
        """Test MetricsHandler initialization."""
        from praisonai.cli.features.metrics import MetricsHandler
        handler = MetricsHandler(verbose=True)
        assert handler.feature_name == "metrics"
        assert handler.flag_name == "metrics"
    
    def test_metrics_apply_to_agent_config(self):
        """Test applying metrics to agent config."""
        from praisonai.cli.features.metrics import MetricsHandler
        handler = MetricsHandler()
        config = {"name": "TestAgent"}
        result = handler.apply_to_agent_config(config, True)
        assert result.get("metrics") is True
    
    def test_metrics_format_output(self):
        """Test formatting metrics output."""
        from praisonai.cli.features.metrics import MetricsHandler
        handler = MetricsHandler()
        
        mock_metrics = {
            "prompt_tokens": 100,
            "completion_tokens": 50,
            "total_tokens": 150,
            "cost": 0.0015
        }
        
        formatted = handler.format_metrics(mock_metrics)
        assert "100" in formatted or "prompt" in formatted.lower()


class TestImageHandler:
    """Tests for --image flag functionality."""
    
    def test_image_handler_import(self):
        """Test that ImageHandler can be imported."""
        from praisonai.cli.features import ImageHandler
        assert ImageHandler is not None
    
    def test_image_handler_initialization(self):
        """Test ImageHandler initialization."""
        from praisonai.cli.features.image import ImageHandler
        handler = ImageHandler(verbose=True)
        assert handler.feature_name == "image"
        assert handler.flag_name == "image"
    
    def test_image_validate_path_valid(self):
        """Test validating a valid image path."""
        from praisonai.cli.features.image import ImageHandler
        handler = ImageHandler()
        
        # Test with a mock path
        with patch('os.path.exists', return_value=True):
            valid, msg = handler.validate_image_path("/path/to/image.png")
            assert valid is True
    
    def test_image_validate_path_invalid_extension(self):
        """Test validating an invalid image extension."""
        from praisonai.cli.features.image import ImageHandler
        handler = ImageHandler()
        
        valid, msg = handler.validate_image_path("/path/to/file.txt")
        assert valid is False
        assert "extension" in msg.lower() or "format" in msg.lower()


class TestTelemetryHandler:
    """Tests for --telemetry flag functionality."""
    
    def test_telemetry_handler_import(self):
        """Test that TelemetryHandler can be imported."""
        from praisonai.cli.features import TelemetryHandler
        assert TelemetryHandler is not None
    
    def test_telemetry_handler_initialization(self):
        """Test TelemetryHandler initialization."""
        from praisonai.cli.features.telemetry import TelemetryHandler
        handler = TelemetryHandler(verbose=True)
        assert handler.feature_name == "telemetry"
        assert handler.flag_name == "telemetry"
    
    def test_telemetry_enable(self):
        """Test enabling telemetry."""
        from praisonai.cli.features.telemetry import TelemetryHandler
        handler = TelemetryHandler()
        
        with patch('praisonai.cli.features.telemetry.enable_telemetry'):
            handler.enable()
            # Should attempt to enable telemetry


class TestMCPHandler:
    """Tests for --mcp flag functionality."""
    
    def test_mcp_handler_import(self):
        """Test that MCPHandler can be imported."""
        from praisonai.cli.features import MCPHandler
        assert MCPHandler is not None
    
    def test_mcp_handler_initialization(self):
        """Test MCPHandler initialization."""
        from praisonai.cli.features.mcp import MCPHandler
        handler = MCPHandler(verbose=True)
        assert handler.feature_name == "mcp"
        assert handler.flag_name == "mcp"
    
    def test_mcp_parse_command_simple(self):
        """Test parsing a simple MCP command."""
        from praisonai.cli.features.mcp import MCPHandler
        handler = MCPHandler()
        
        command, args, env = handler.parse_mcp_command("npx -y @modelcontextprotocol/server-filesystem .")
        assert command == "npx"
        assert "-y" in args
        assert isinstance(env, dict)
    
    def test_mcp_parse_command_with_env(self):
        """Test parsing MCP command with environment variables."""
        from praisonai.cli.features.mcp import MCPHandler
        handler = MCPHandler()
        
        result = handler.parse_mcp_command(
            "npx server",
            env_vars="API_KEY=test123,DEBUG=true"
        )
        assert result is not None


class TestFastContextHandler:
    """Tests for --fast-context flag functionality."""
    
    def test_fast_context_handler_import(self):
        """Test that FastContextHandler can be imported."""
        from praisonai.cli.features import FastContextHandler
        assert FastContextHandler is not None
    
    def test_fast_context_handler_initialization(self):
        """Test FastContextHandler initialization."""
        from praisonai.cli.features.fast_context import FastContextHandler
        handler = FastContextHandler(verbose=True)
        assert handler.feature_name == "fast_context"
        assert handler.flag_name == "fast-context"
    
    def test_fast_context_validate_path(self):
        """Test validating search path."""
        from praisonai.cli.features.fast_context import FastContextHandler
        handler = FastContextHandler()
        
        with patch('os.path.isdir', return_value=True):
            valid, msg = handler.validate_search_path("/valid/path")
            assert valid is True


class TestKnowledgeHandler:
    """Tests for knowledge command functionality."""
    
    def test_knowledge_handler_import(self):
        """Test that KnowledgeHandler can be imported."""
        from praisonai.cli.features import KnowledgeHandler
        assert KnowledgeHandler is not None
    
    def test_knowledge_handler_initialization(self):
        """Test KnowledgeHandler initialization."""
        from praisonai.cli.features.knowledge import KnowledgeHandler
        handler = KnowledgeHandler(verbose=True)
        assert handler.feature_name == "knowledge"
    
    def test_knowledge_get_actions(self):
        """Test getting available actions."""
        from praisonai.cli.features.knowledge import KnowledgeHandler
        handler = KnowledgeHandler()
        actions = handler.get_actions()
        assert "add" in actions
        assert "search" in actions
        assert "list" in actions


class TestSessionHandler:
    """Tests for session command functionality."""
    
    def test_session_handler_import(self):
        """Test that SessionHandler can be imported."""
        from praisonai.cli.features import SessionHandler
        assert SessionHandler is not None
    
    def test_session_handler_initialization(self):
        """Test SessionHandler initialization."""
        from praisonai.cli.features.session import SessionHandler
        handler = SessionHandler(verbose=True)
        assert handler.feature_name == "session"
    
    def test_session_get_actions(self):
        """Test getting available actions."""
        from praisonai.cli.features.session import SessionHandler
        handler = SessionHandler()
        actions = handler.get_actions()
        assert "list" in actions
        assert "show" in actions
        assert "resume" in actions
        assert "delete" in actions


class TestToolsHandler:
    """Tests for tools command functionality."""
    
    def test_tools_handler_import(self):
        """Test that ToolsHandler can be imported."""
        from praisonai.cli.features import ToolsHandler
        assert ToolsHandler is not None
    
    def test_tools_handler_initialization(self):
        """Test ToolsHandler initialization."""
        from praisonai.cli.features.tools import ToolsHandler
        handler = ToolsHandler(verbose=True)
        assert handler.feature_name == "tools"
    
    def test_tools_get_actions(self):
        """Test getting available actions."""
        from praisonai.cli.features.tools import ToolsHandler
        handler = ToolsHandler()
        actions = handler.get_actions()
        assert "list" in actions
        assert "info" in actions


class TestHandoffHandler:
    """Tests for --handoff flag functionality."""
    
    def test_handoff_handler_import(self):
        """Test that HandoffHandler can be imported."""
        from praisonai.cli.features import HandoffHandler
        assert HandoffHandler is not None
    
    def test_handoff_handler_initialization(self):
        """Test HandoffHandler initialization."""
        from praisonai.cli.features.handoff import HandoffHandler
        handler = HandoffHandler(verbose=True)
        assert handler.feature_name == "handoff"
        assert handler.flag_name == "handoff"
    
    def test_handoff_parse_agents(self):
        """Test parsing agent names from comma-separated string."""
        from praisonai.cli.features.handoff import HandoffHandler
        handler = HandoffHandler()
        
        agents = handler.parse_agent_names("researcher,writer,editor")
        assert len(agents) == 3
        assert "researcher" in agents


class TestAutoMemoryHandler:
    """Tests for --auto-memory flag functionality."""
    
    def test_auto_memory_handler_import(self):
        """Test that AutoMemoryHandler can be imported."""
        from praisonai.cli.features import AutoMemoryHandler
        assert AutoMemoryHandler is not None
    
    def test_auto_memory_handler_initialization(self):
        """Test AutoMemoryHandler initialization."""
        from praisonai.cli.features.auto_memory import AutoMemoryHandler
        handler = AutoMemoryHandler(verbose=True)
        assert handler.feature_name == "auto_memory"
        assert handler.flag_name == "auto-memory"


class TestTodoHandler:
    """Tests for todo command and --todo flag functionality."""
    
    def test_todo_handler_import(self):
        """Test that TodoHandler can be imported."""
        from praisonai.cli.features import TodoHandler
        assert TodoHandler is not None
    
    def test_todo_handler_initialization(self):
        """Test TodoHandler initialization."""
        from praisonai.cli.features.todo import TodoHandler
        handler = TodoHandler(verbose=True)
        assert handler.feature_name == "todo"
    
    def test_todo_get_actions(self):
        """Test getting available actions."""
        from praisonai.cli.features.todo import TodoHandler
        handler = TodoHandler()
        actions = handler.get_actions()
        assert "list" in actions
        assert "add" in actions


class TestRouterHandler:
    """Tests for --router flag functionality."""
    
    def test_router_handler_import(self):
        """Test that RouterHandler can be imported."""
        from praisonai.cli.features import RouterHandler
        assert RouterHandler is not None
    
    def test_router_handler_initialization(self):
        """Test RouterHandler initialization."""
        from praisonai.cli.features.router import RouterHandler
        handler = RouterHandler(verbose=True)
        assert handler.feature_name == "router"
        assert handler.flag_name == "router"


class TestFlowDisplayHandler:
    """Tests for --flow-display flag functionality."""
    
    def test_flow_display_handler_import(self):
        """Test that FlowDisplayHandler can be imported."""
        from praisonai.cli.features import FlowDisplayHandler
        assert FlowDisplayHandler is not None
    
    def test_flow_display_handler_initialization(self):
        """Test FlowDisplayHandler initialization."""
        from praisonai.cli.features.flow_display import FlowDisplayHandler
        handler = FlowDisplayHandler(verbose=True)
        assert handler.feature_name == "flow_display"
        assert handler.flag_name == "flow-display"


class TestCLIArgumentParsing:
    """Tests for CLI argument parsing of new features."""
    
    def test_guardrail_argument_parsed(self):
        """Test that --guardrail argument is parsed correctly."""
        from praisonai.cli import PraisonAI
        
        with patch.object(sys, 'argv', ['praisonai', '--guardrail', 'Check output']):
            PraisonAI()  # Just verify no exception is raised
    
    def test_metrics_argument_parsed(self):
        """Test that --metrics argument is parsed correctly."""
        from praisonai.cli import PraisonAI
        
        with patch.object(sys, 'argv', ['praisonai', '--metrics']):
            PraisonAI()  # Just verify no exception is raised
    
    def test_image_argument_parsed(self):
        """Test that --image argument is parsed correctly."""
        from praisonai.cli import PraisonAI
        
        with patch.object(sys, 'argv', ['praisonai', '--image', '/path/to/image.png']):
            PraisonAI()  # Just verify no exception is raised


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short", "-x"])
