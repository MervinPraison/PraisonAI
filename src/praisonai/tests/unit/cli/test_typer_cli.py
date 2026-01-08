"""
Tests for PraisonAI Typer CLI.

Tests the new modular Typer-based CLI structure.
"""

import json
import os
import pytest
from pathlib import Path
from typer.testing import CliRunner
from unittest.mock import patch, MagicMock


# Create CLI runner
runner = CliRunner()


class TestTyperApp:
    """Tests for the main Typer app."""
    
    def test_app_import(self):
        """Test that the Typer app can be imported."""
        from praisonai.cli.app import app
        assert app is not None
    
    def test_help_output(self):
        """Test --help shows expected content."""
        from praisonai.cli.app import app
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "PraisonAI" in result.output
        assert "config" in result.output
        assert "traces" in result.output
        assert "session" in result.output
    
    def test_version_flag(self):
        """Test --version flag."""
        from praisonai.cli.app import app
        result = runner.invoke(app, ["--version"])
        assert result.exit_code == 0
        assert "PraisonAI version" in result.output


class TestConfigCommand:
    """Tests for config command group."""
    
    def test_config_list(self):
        """Test config list command."""
        from praisonai.cli.commands.config import app
        result = runner.invoke(app, ["list"])
        assert result.exit_code == 0
    
    def test_config_get_missing_key(self):
        """Test config get with missing key."""
        from praisonai.cli.commands.config import app
        result = runner.invoke(app, ["get", "nonexistent.key"])
        assert result.exit_code == 1
        assert "not found" in result.output.lower()
    
    def test_config_path(self):
        """Test config path command."""
        from praisonai.cli.commands.config import app
        result = runner.invoke(app, ["path"])
        assert result.exit_code == 0
        assert "config.toml" in result.output


class TestTracesCommand:
    """Tests for traces command group."""
    
    def test_traces_status(self):
        """Test traces status command."""
        from praisonai.cli.commands.traces import app
        result = runner.invoke(app, ["status"])
        assert result.exit_code == 0
        assert "Trace" in result.output or "trace" in result.output.lower()
    
    def test_traces_enable(self):
        """Test traces enable command."""
        from praisonai.cli.commands.traces import app
        result = runner.invoke(app, ["enable"])
        assert result.exit_code == 0


class TestEnvCommand:
    """Tests for env command group."""
    
    def test_env_view(self):
        """Test env view command."""
        from praisonai.cli.commands.environment import app
        result = runner.invoke(app, ["view"])
        # Should succeed even if no env vars found
        assert result.exit_code == 0
    
    def test_env_check(self):
        """Test env check command."""
        from praisonai.cli.commands.environment import app
        result = runner.invoke(app, ["check"])
        # May exit with 3 if keys are missing, but should not crash
        assert result.exit_code in [0, 3]


class TestSessionCommand:
    """Tests for session command group."""
    
    def test_session_list(self):
        """Test session list command."""
        from praisonai.cli.commands.session import app
        result = runner.invoke(app, ["list"])
        assert result.exit_code == 0


class TestCompletionCommand:
    """Tests for completion command group."""
    
    def test_completion_bash(self):
        """Test bash completion generation."""
        from praisonai.cli.commands.completion import app
        result = runner.invoke(app, ["bash"])
        assert result.exit_code == 0
        assert "praisonai" in result.output
        assert "complete" in result.output or "COMPREPLY" in result.output
    
    def test_completion_zsh(self):
        """Test zsh completion generation."""
        from praisonai.cli.commands.completion import app
        result = runner.invoke(app, ["zsh"])
        assert result.exit_code == 0
        assert "praisonai" in result.output
        assert "compdef" in result.output or "_praisonai" in result.output
    
    def test_completion_fish(self):
        """Test fish completion generation."""
        from praisonai.cli.commands.completion import app
        result = runner.invoke(app, ["fish"])
        assert result.exit_code == 0
        assert "praisonai" in result.output
        assert "complete" in result.output


class TestVersionCommand:
    """Tests for version command group."""
    
    def test_version_show(self):
        """Test version show command."""
        from praisonai.cli.commands.version import app
        result = runner.invoke(app, ["show"])
        assert result.exit_code == 0
        assert "PraisonAI" in result.output or "praisonai" in result.output.lower()


class TestMCPCommand:
    """Tests for MCP command group."""
    
    def test_mcp_list(self):
        """Test mcp list command."""
        from praisonai.cli.commands.mcp import app
        result = runner.invoke(app, ["list"])
        assert result.exit_code == 0


class TestOutputController:
    """Tests for output controller."""
    
    def test_output_modes(self):
        """Test output mode enumeration."""
        from praisonai.cli.output.console import OutputMode
        assert OutputMode.TEXT == "text"
        assert OutputMode.JSON == "json"
        assert OutputMode.STREAM_JSON == "stream-json"
        assert OutputMode.SCREEN_READER == "screen-reader"
        assert OutputMode.QUIET == "quiet"
        assert OutputMode.VERBOSE == "verbose"
    
    def test_output_controller_creation(self):
        """Test output controller creation."""
        from praisonai.cli.output.console import OutputController, OutputMode
        
        controller = OutputController(mode=OutputMode.TEXT)
        assert controller.mode == OutputMode.TEXT
        assert not controller.is_json_mode
        
        controller = OutputController(mode=OutputMode.JSON)
        assert controller.is_json_mode
    
    def test_stream_event(self):
        """Test stream event creation."""
        from praisonai.cli.output.console import StreamEvent
        
        event = StreamEvent(
            event_type="start",
            run_id="run_123",
            trace_id="trace_456",
            message="Test message"
        )
        
        data = event.to_dict()
        assert data["event"] == "start"
        assert data["run_id"] == "run_123"
        assert data["trace_id"] == "trace_456"
        assert data["message"] == "Test message"
        assert "timestamp" in data


class TestConfigurationSystem:
    """Tests for configuration system."""
    
    def test_config_schema(self):
        """Test config schema creation."""
        from praisonai.cli.configuration.schema import ConfigSchema, DEFAULT_CONFIG
        
        assert DEFAULT_CONFIG is not None
        assert DEFAULT_CONFIG.output.format == "text"
        assert DEFAULT_CONFIG.traces.enabled == False
    
    def test_config_to_dict(self):
        """Test config to dict conversion."""
        from praisonai.cli.configuration.schema import ConfigSchema
        
        config = ConfigSchema()
        data = config.to_dict()
        
        assert "output" in data
        assert "traces" in data
        assert "mcp" in data
        assert "model" in data
        assert "session" in data
    
    def test_config_from_dict(self):
        """Test config from dict creation."""
        from praisonai.cli.configuration.schema import ConfigSchema
        
        data = {
            "output": {"format": "json", "verbose": True},
            "traces": {"enabled": True},
        }
        
        config = ConfigSchema.from_dict(data)
        assert config.output.format == "json"
        assert config.output.verbose == True
        assert config.traces.enabled == True
    
    def test_config_paths(self):
        """Test config paths."""
        from praisonai.cli.configuration.paths import (
            get_user_config_path,
            get_project_config_path,
            get_sessions_dir,
        )
        
        user_path = get_user_config_path()
        assert user_path.name == "config.toml"
        assert ".praison" in str(user_path)
        
        project_path = get_project_config_path()
        assert project_path.name == "config.toml"
        
        sessions_dir = get_sessions_dir()
        assert "sessions" in str(sessions_dir)


class TestStateManagement:
    """Tests for state management."""
    
    def test_run_id_generation(self):
        """Test run ID generation."""
        from praisonai.cli.state.identifiers import generate_run_id
        
        run_id = generate_run_id()
        assert run_id.startswith("run_")
        assert len(run_id) > 10
    
    def test_trace_id_generation(self):
        """Test trace ID generation."""
        from praisonai.cli.state.identifiers import generate_trace_id
        
        trace_id = generate_trace_id()
        assert trace_id.startswith("trace_")
    
    def test_agent_id_generation(self):
        """Test agent ID generation is deterministic."""
        from praisonai.cli.state.identifiers import generate_agent_id
        
        agent_id1 = generate_agent_id("test_agent", "run_123", 0)
        agent_id2 = generate_agent_id("test_agent", "run_123", 0)
        
        assert agent_id1 == agent_id2
        assert agent_id1.startswith("agent_")
    
    def test_run_context(self):
        """Test run context creation."""
        from praisonai.cli.state.identifiers import RunContext
        
        ctx = RunContext()
        assert ctx.run_id.startswith("run_")
        assert ctx.trace_id.startswith("trace_")
        
        # Test agent ID tracking
        agent_id = ctx.get_agent_id("test_agent")
        assert agent_id.startswith("agent_")
        
        # Same agent should get same ID
        agent_id2 = ctx.get_agent_id("test_agent")
        assert agent_id == agent_id2
    
    def test_context_to_dict(self):
        """Test context serialization."""
        from praisonai.cli.state.identifiers import RunContext
        
        ctx = RunContext(workspace="/test")
        ctx.get_agent_id("agent1")
        
        data = ctx.to_dict()
        assert "run_id" in data
        assert "trace_id" in data
        assert "agents" in data
        assert data["workspace"] == "/test"


class TestSessionManager:
    """Tests for session manager."""
    
    def test_session_metadata(self):
        """Test session metadata creation."""
        from praisonai.cli.state.sessions import SessionMetadata
        from datetime import datetime
        
        now = datetime.utcnow()
        metadata = SessionMetadata(
            session_id="test_session",
            run_id="run_123",
            trace_id="trace_456",
            created_at=now,
            updated_at=now,
            name="Test Session",
        )
        
        assert metadata.session_id == "test_session"
        assert metadata.name == "Test Session"
        
        data = metadata.to_dict()
        assert data["session_id"] == "test_session"
        assert data["name"] == "Test Session"


class TestLegacyCompatibility:
    """Tests for legacy compatibility."""
    
    def test_is_legacy_invocation(self):
        """Test legacy invocation detection."""
        from praisonai.cli.legacy import is_legacy_invocation
        
        # Legacy patterns (flags that trigger legacy mode)
        assert is_legacy_invocation(["--framework", "crewai"])
        assert is_legacy_invocation(["--auto", "test"])
        
        # Typer patterns (commands now in TYPER_COMMANDS)
        assert not is_legacy_invocation(["chat"])  # Now a Typer command
        assert not is_legacy_invocation(["config", "list"])
        assert not is_legacy_invocation(["version", "show"])
    
    def test_typer_commands_set(self):
        """Test TYPER_COMMANDS contains expected commands."""
        from praisonai.cli.legacy import TYPER_COMMANDS
        
        expected = {'config', 'traces', 'env', 'session', 'completion', 'version',
                    'debug', 'lsp', 'diag', 'doctor', 'acp', 'mcp', 'serve', 'schedule', 'run'}
        
        for cmd in expected:
            assert cmd in TYPER_COMMANDS


class TestGlobalOptions:
    """Tests for global CLI options."""
    
    def test_json_output_option(self):
        """Test --json option."""
        from praisonai.cli.app import app
        result = runner.invoke(app, ["--json", "config", "list"])
        # Should produce JSON output
        assert result.exit_code == 0
    
    def test_quiet_option(self):
        """Test --quiet option."""
        from praisonai.cli.app import app
        result = runner.invoke(app, ["--quiet", "version", "show"])
        assert result.exit_code == 0
    
    def test_no_color_option(self):
        """Test --no-color option."""
        from praisonai.cli.app import app
        result = runner.invoke(app, ["--no-color", "version", "show"])
        assert result.exit_code == 0


class TestExitCodes:
    """Tests for deterministic exit codes."""
    
    def test_success_exit_code(self):
        """Test success returns 0."""
        from praisonai.cli.app import app
        result = runner.invoke(app, ["version", "show"])
        assert result.exit_code == 0
    
    def test_usage_error_exit_code(self):
        """Test usage error returns 2."""
        from praisonai.cli.app import app
        result = runner.invoke(app, ["config", "get"])  # Missing required arg
        assert result.exit_code == 2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
