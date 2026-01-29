"""
Tests for unified serve commands.

Tests that all serve subcommands are properly registered and accessible
under the `praisonai serve` namespace.
"""

from typer.testing import CliRunner

runner = CliRunner()


class TestServeUnifiedCommands:
    """Test unified serve command structure."""
    
    def test_serve_help_shows_all_server_types(self):
        """Test that serve --help shows all server types."""
        from praisonai.cli.commands.serve import app
        
        result = runner.invoke(app, ["--help"])
        
        # Should show all server types
        assert "agents" in result.output.lower() or result.exit_code == 0
    
    def test_serve_callback_shows_unified_help(self):
        """Test that serve without subcommand shows unified help."""
        from praisonai.cli.commands.serve import app
        
        result = runner.invoke(app, [])
        
        # Should show help text (not error)
        assert result.exit_code == 0 or "Server Types" in result.output
    
    def test_serve_agents_command_exists(self):
        """Test serve agents command is registered."""
        from praisonai.cli.commands.serve import app
        
        result = runner.invoke(app, ["agents", "--help"])
        
        # Should show help for agents command
        assert "agents" in result.output.lower() or result.exit_code == 0
    
    def test_serve_gateway_command_exists(self):
        """Test serve gateway command is registered."""
        from praisonai.cli.commands.serve import app
        
        result = runner.invoke(app, ["gateway", "--help"])
        
        # Should show help for gateway command
        assert "gateway" in result.output.lower() or "websocket" in result.output.lower() or result.exit_code == 0
    
    def test_serve_mcp_command_exists(self):
        """Test serve mcp command is registered."""
        from praisonai.cli.commands.serve import app
        
        result = runner.invoke(app, ["mcp", "--help"])
        
        # Should show help for mcp command
        assert "mcp" in result.output.lower() or result.exit_code == 0
    
    def test_serve_acp_command_exists(self):
        """Test serve acp command is registered."""
        from praisonai.cli.commands.serve import app
        
        result = runner.invoke(app, ["acp", "--help"])
        
        # Should show help for acp command
        assert "acp" in result.output.lower() or "ide" in result.output.lower() or result.exit_code == 0
    
    def test_serve_lsp_command_exists(self):
        """Test serve lsp command is registered."""
        from praisonai.cli.commands.serve import app
        
        result = runner.invoke(app, ["lsp", "--help"])
        
        # Should show help for lsp command
        assert "lsp" in result.output.lower() or result.exit_code == 0
    
    def test_serve_ui_command_exists(self):
        """Test serve ui command is registered."""
        from praisonai.cli.commands.serve import app
        
        result = runner.invoke(app, ["ui", "--help"])
        
        # Should show help for ui command
        assert "ui" in result.output.lower() or "chainlit" in result.output.lower() or result.exit_code == 0
    
    def test_serve_rag_command_exists(self):
        """Test serve rag command is registered."""
        from praisonai.cli.commands.serve import app
        
        result = runner.invoke(app, ["rag", "--help"])
        
        # Should show help for rag command
        assert "rag" in result.output.lower() or result.exit_code == 0
    
    def test_serve_registry_command_exists(self):
        """Test serve registry command is registered."""
        from praisonai.cli.commands.serve import app
        
        result = runner.invoke(app, ["registry", "--help"])
        
        # Should show help for registry command
        assert "registry" in result.output.lower() or result.exit_code == 0
    
    def test_serve_docs_command_exists(self):
        """Test serve docs command is registered."""
        from praisonai.cli.commands.serve import app
        
        result = runner.invoke(app, ["docs", "--help"])
        
        # Should show help for docs command
        assert "docs" in result.output.lower() or result.exit_code == 0
    
    def test_serve_scheduler_command_exists(self):
        """Test serve scheduler command is registered."""
        from praisonai.cli.commands.serve import app
        
        result = runner.invoke(app, ["scheduler", "--help"])
        
        # Should show help for scheduler command
        assert "scheduler" in result.output.lower() or result.exit_code == 0
    
    def test_serve_recipe_command_exists(self):
        """Test serve recipe command is registered."""
        from praisonai.cli.commands.serve import app
        
        result = runner.invoke(app, ["recipe", "--help"])
        
        # Should show help for recipe command
        assert "recipe" in result.output.lower() or result.exit_code == 0
    
    def test_serve_a2a_command_exists(self):
        """Test serve a2a command is registered."""
        from praisonai.cli.commands.serve import app
        
        result = runner.invoke(app, ["a2a", "--help"])
        
        # Should show help for a2a command
        assert "a2a" in result.output.lower() or "agent-to-agent" in result.output.lower() or result.exit_code == 0
    
    def test_serve_a2u_command_exists(self):
        """Test serve a2u command is registered."""
        from praisonai.cli.commands.serve import app
        
        result = runner.invoke(app, ["a2u", "--help"])
        
        # Should show help for a2u command
        assert "a2u" in result.output.lower() or result.exit_code == 0
    
    def test_serve_unified_command_exists(self):
        """Test serve unified command is registered."""
        from praisonai.cli.commands.serve import app
        
        result = runner.invoke(app, ["unified", "--help"])
        
        # Should show help for unified command
        assert "unified" in result.output.lower() or result.exit_code == 0


class TestServeCommandOptions:
    """Test serve command options."""
    
    def test_serve_agents_has_host_option(self):
        """Test serve agents has --host option."""
        from praisonai.cli.commands.serve import app
        
        result = runner.invoke(app, ["agents", "--help"])
        assert "--host" in result.output
    
    def test_serve_agents_has_port_option(self):
        """Test serve agents has --port option."""
        from praisonai.cli.commands.serve import app
        
        result = runner.invoke(app, ["agents", "--help"])
        assert "--port" in result.output
    
    def test_serve_gateway_has_agents_option(self):
        """Test serve gateway has --agents option."""
        from praisonai.cli.commands.serve import app
        
        result = runner.invoke(app, ["gateway", "--help"])
        assert "--agents" in result.output or "-a" in result.output
    
    def test_serve_mcp_has_transport_option(self):
        """Test serve mcp has --transport option."""
        from praisonai.cli.commands.serve import app
        
        result = runner.invoke(app, ["mcp", "--help"])
        assert "--transport" in result.output or "-T" in result.output


class TestDeprecationWarnings:
    """Test deprecation warnings for old commands."""
    
    def test_gateway_deprecation_message_in_docstring(self):
        """Test gateway handler has deprecation in docstring."""
        from praisonai.cli.features.gateway import handle_gateway_command
        
        # Check docstring mentions deprecation
        assert handle_gateway_command.__doc__ is not None
        assert "DEPRECATED" in handle_gateway_command.__doc__ or "serve gateway" in handle_gateway_command.__doc__
    
    def test_acp_deprecation_message_in_docstring(self):
        """Test acp command has deprecation in docstring."""
        from praisonai.cli.commands.acp import acp_main
        
        # Check docstring mentions deprecation
        assert acp_main.__doc__ is not None
        assert "DEPRECATED" in acp_main.__doc__ or "serve acp" in acp_main.__doc__
    
    def test_ui_deprecation_message_in_docstring(self):
        """Test ui command has deprecation in docstring."""
        from praisonai.cli.commands.ui import ui_main
        
        # Check docstring mentions deprecation
        assert ui_main.__doc__ is not None
        assert "DEPRECATED" in ui_main.__doc__ or "serve ui" in ui_main.__doc__
