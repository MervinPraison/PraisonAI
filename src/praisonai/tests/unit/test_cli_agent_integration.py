"""
Integration tests for CLI features with Agent execution.

These tests verify that CLI features are properly integrated into
the agent execution flow in handle_direct_prompt().
"""

import pytest
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))


class TestAgentFeatureIntegration:
    """Tests for CLI features integrated with agent execution."""
    
    def test_router_handler_integration(self):
        """Test that RouterHandler can select model for agent."""
        from praisonai.cli.features.router import RouterHandler
        
        handler = RouterHandler()
        model = handler.select_model("Simple question")
        assert model is not None
        assert isinstance(model, str)
    
    def test_metrics_handler_integration(self):
        """Test that MetricsHandler can be applied to agent config."""
        from praisonai.cli.features.metrics import MetricsHandler
        
        handler = MetricsHandler()
        config = {"name": "TestAgent"}
        result = handler.apply_to_agent_config(config, True)
        assert result.get("metrics") is True
    
    def test_mcp_handler_integration(self):
        """Test that MCPHandler can parse MCP commands."""
        from praisonai.cli.features.mcp import MCPHandler
        
        handler = MCPHandler()
        cmd, args, env = handler.parse_mcp_command("npx -y @mcp/server .")
        assert cmd == "npx"
        assert "-y" in args
    
    def test_fast_context_handler_integration(self):
        """Test that FastContextHandler can validate paths."""
        from praisonai.cli.features.fast_context import FastContextHandler
        
        handler = FastContextHandler()
        valid, msg = handler.validate_search_path("/tmp")
        # /tmp should exist on most systems
        assert isinstance(valid, bool)
    
    def test_guardrail_handler_integration(self):
        """Test that GuardrailHandler can be applied to config."""
        from praisonai.cli.features.guardrail import GuardrailHandler
        
        handler = GuardrailHandler()
        config = {"name": "TestAgent"}
        result = handler.apply_to_agent_config(config, "Check output")
        assert "guardrail_description" in result
    
    def test_todo_handler_integration(self):
        """Test that TodoHandler can extract todos from text."""
        from praisonai.cli.features.todo import TodoHandler
        
        handler = TodoHandler()
        todos = handler.generate_todos_from_response("1. First task\n2. Second task\n3. Third task")
        assert len(todos) == 3
        assert todos[0]['task'] == "First task"
    
    def test_auto_memory_handler_integration(self):
        """Test that AutoMemoryHandler can be applied to config."""
        from praisonai.cli.features.auto_memory import AutoMemoryHandler
        
        handler = AutoMemoryHandler()
        config = {"name": "TestAgent"}
        result = handler.apply_to_agent_config(config, True)
        assert result.get("auto_memory") is True
    
    def test_image_handler_integration(self):
        """Test that ImageHandler can validate image paths."""
        from praisonai.cli.features.image import ImageHandler
        
        handler = ImageHandler()
        valid, msg = handler.validate_image_path("/path/to/image.png")
        # Path doesn't exist, but extension is valid
        assert "not found" in msg.lower() or valid is False
        
        valid2, msg2 = handler.validate_image_path("/path/to/file.txt")
        assert valid2 is False
        assert "format" in msg2.lower() or "extension" in msg2.lower()
    
    def test_handoff_handler_integration(self):
        """Test that HandoffHandler can parse agent names."""
        from praisonai.cli.features.handoff import HandoffHandler
        
        handler = HandoffHandler()
        agents = handler.parse_agent_names("researcher,writer,editor")
        assert len(agents) == 3
        assert "researcher" in agents
        assert "writer" in agents
        assert "editor" in agents
    
    def test_telemetry_handler_integration(self):
        """Test that TelemetryHandler can check dependencies."""
        from praisonai.cli.features.telemetry import TelemetryHandler
        
        handler = TelemetryHandler()
        available, msg = handler.check_dependencies()
        assert isinstance(available, bool)
    
    def test_flow_display_handler_integration(self):
        """Test that FlowDisplayHandler can display workflow."""
        from praisonai.cli.features.flow_display import FlowDisplayHandler
        
        handler = FlowDisplayHandler()
        # Should not raise
        handler.display_workflow_start("Test Workflow", ["Agent1", "Agent2"])
        handler.display_workflow_end(success=True)


class TestAgentConfigApplication:
    """Tests for verifying features are applied to agent config."""
    
    def test_metrics_in_agent_config(self):
        """Verify metrics flag is applied to agent config."""
        from praisonai.cli.features.metrics import MetricsHandler
        
        handler = MetricsHandler()
        config = {"name": "TestAgent"}
        result = handler.apply_to_agent_config(config, True)
        
        assert result.get("metrics") is True
    
    def test_guardrail_in_agent_config(self):
        """Verify guardrail is stored for post-processing."""
        from praisonai.cli.features.guardrail import GuardrailHandler
        
        handler = GuardrailHandler()
        config = {"name": "TestAgent"}
        result = handler.apply_to_agent_config(config, "Check validity")
        
        assert "guardrail_description" in result
    
    def test_router_selects_appropriate_model(self):
        """Verify router selects model based on complexity."""
        from praisonai.cli.features.router import RouterHandler
        
        handler = RouterHandler()
        
        # Simple prompt should get simpler model
        simple_model = handler.select_model("What is 2+2?")
        assert simple_model in ['gpt-4o-mini', 'claude-3-haiku', 'gemini-1.5-flash']
        
        # Complex prompt should get more capable model
        complex_model = handler.select_model(
            "Analyze the comprehensive architecture of this system, "
            "evaluate all design patterns, and synthesize a detailed report"
        )
        assert complex_model in ['gpt-4-turbo', 'claude-3-opus', 'o1-preview', 'gpt-4o', 'claude-3-sonnet', 'gemini-1.5-pro']


class TestBarePositionalPrompt:
    """Tests for treating a bare positional argument as a one-shot prompt."""

    def _run_with_command(self, command):
        from unittest.mock import patch, MagicMock
        from praisonai.cli.main import PraisonAI

        instance = PraisonAI()
        instance.agent_file = "agents.yaml"

        mock_generator = MagicMock()
        mock_generator.generate_crew_and_kickoff.return_value = "AGENT_FILE_RUN"

        # Build a fully-populated args namespace (all CLI defaults) and set the
        # positional command, then feed it to main() via a patched parse_args.
        base_args = instance.parse_args()
        if isinstance(base_args, tuple):
            base_args = base_args[0]
        base_args.command = command

        with patch.object(PraisonAI, "parse_args", return_value=(base_args, [])), \
             patch.object(PraisonAI, "read_stdin_if_available", return_value=None), \
             patch.object(PraisonAI, "read_file_if_provided", return_value=None), \
             patch("praisonai.cli.main._get_agents_generator", return_value=lambda *a, **k: mock_generator), \
             patch.object(PraisonAI, "handle_direct_prompt", return_value="OK") as mock_prompt:
            result = instance.run()
        return instance, mock_prompt, result, mock_generator

    def test_bare_prompt_routes_to_direct_prompt(self):
        """A non-file, non-YAML positional is run as a one-shot prompt."""
        instance, mock_prompt, result, _ = self._run_with_command("summarise this folder")
        mock_prompt.assert_called_once_with("summarise this folder")
        assert result == "OK"

    def test_yaml_path_kept_as_agent_file(self):
        """A .yaml positional is preserved as the agent file (not a prompt)."""
        instance, mock_prompt, _, mock_generator = self._run_with_command("agents.yaml")
        mock_prompt.assert_not_called()
        assert instance.agent_file == "agents.yaml"

    def test_existing_file_kept_as_agent_file(self, tmp_path):
        """An existing file path is preserved as the agent file."""
        f = tmp_path / "custom_agents.txt"
        f.write_text("framework: praisonai")
        instance, mock_prompt, _, _ = self._run_with_command(str(f))
        mock_prompt.assert_not_called()
        assert instance.agent_file == str(f)

    def _parse_real(self, command, *, isfile=False):
        """Drive the real parse_args() disambiguation as production would.

        parse_args() short-circuits under pytest, so temporarily mask the
        test-environment signals and feed a realistic ``sys.argv`` to exercise
        the actual positional-vs-prompt routing logic.
        """
        from unittest.mock import patch
        from praisonai.cli.main import PraisonAI

        instance = PraisonAI()
        clean_env = {k: v for k, v in os.environ.items() if k != "PYTEST_CURRENT_TEST"}
        with patch.object(sys, "argv", ["praisonai", command]), \
             patch.dict(os.environ, clean_env, clear=True), \
             patch("os.path.isfile", return_value=isfile):
            result = instance.parse_args()
        args = result[0] if isinstance(result, tuple) else result
        return args

    def test_real_parse_bare_prompt_becomes_direct_prompt(self):
        """Real parse_args routes a bare prompt to direct_prompt."""
        args = self._parse_real("summarise this folder")
        assert args.command is None
        assert args.direct_prompt == "summarise this folder"

    def test_real_parse_uppercase_yaml_kept_as_command(self):
        """Real parse_args keeps an uppercase .YAML path as the agent file."""
        args = self._parse_real("Agents.YAML")
        assert args.command == "Agents.YAML"

    def test_real_parse_yml_path_kept_as_command(self):
        """Real parse_args keeps a .yml path as the agent file."""
        args = self._parse_real("workflow.yml")
        assert args.command == "workflow.yml"

    def test_real_parse_existing_file_kept_as_command(self):
        """Real parse_args keeps an existing non-YAML file as the agent file."""
        args = self._parse_real("custom_agents.txt", isfile=True)
        assert args.command == "custom_agents.txt"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
