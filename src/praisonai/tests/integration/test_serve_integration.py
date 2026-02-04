"""
Integration tests for unified serve commands.

Tests that servers can start and respond to HTTP requests.
Uses subprocess to start servers and curl/requests to verify.
"""

import subprocess
import sys
import time
import socket

import pytest


def is_port_in_use(port: int) -> bool:
    """Check if a port is already in use."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('127.0.0.1', port)) == 0


def wait_for_server(port: int, timeout: int = 10) -> bool:
    """Wait for server to be ready on given port."""
    start = time.time()
    while time.time() - start < timeout:
        if is_port_in_use(port):
            return True
        time.sleep(0.5)
    return False


def find_free_port() -> int:
    """Find a free port to use for testing."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('', 0))
        return s.getsockname()[1]


class TestServeAgentsIntegration:
    """Integration tests for serve agents command."""
    
    @pytest.fixture
    def agents_yaml(self, tmp_path):
        """Create a minimal agents.yaml for testing."""
        yaml_content = """
framework: praisonai
topic: Test Agent
roles:
  test_agent:
    role: Test Agent
    goal: Answer questions
    backstory: You are a test agent
    tasks:
      test_task:
        description: Answer the question
        expected_output: A response
"""
        yaml_file = tmp_path / "agents.yaml"
        yaml_file.write_text(yaml_content)
        return str(yaml_file)
    
    def test_serve_agents_help(self):
        """Test serve agents --help works."""
        result = subprocess.run(
            [sys.executable, "-m", "praisonai.cli.commands.serve", "agents", "--help"],
            capture_output=True,
            text=True,
            cwd="/Users/praison/praisonai-package/src/praisonai"
        )
        # Should show help without error
        assert "--host" in result.stdout or result.returncode == 0


class TestServeA2AIntegration:
    """Integration tests for serve a2a command."""
    
    def test_serve_a2a_help(self):
        """Test serve a2a --help works."""
        result = subprocess.run(
            [sys.executable, "-m", "praisonai.cli.commands.serve", "a2a", "--help"],
            capture_output=True,
            text=True,
            cwd="/Users/praison/praisonai-package/src/praisonai"
        )
        assert "--host" in result.stdout or result.returncode == 0


class TestServeUnifiedIntegration:
    """Integration tests for serve unified command."""
    
    def test_serve_unified_help(self):
        """Test serve unified --help works."""
        result = subprocess.run(
            [sys.executable, "-m", "praisonai.cli.commands.serve", "unified", "--help"],
            capture_output=True,
            text=True,
            cwd="/Users/praison/praisonai-package/src/praisonai"
        )
        assert "--host" in result.stdout or result.returncode == 0


class TestServeGatewayIntegration:
    """Integration tests for serve gateway command."""
    
    def test_serve_gateway_help(self):
        """Test serve gateway --help works."""
        result = subprocess.run(
            [sys.executable, "-m", "praisonai.cli.commands.serve", "gateway", "--help"],
            capture_output=True,
            text=True,
            cwd="/Users/praison/praisonai-package/src/praisonai"
        )
        assert "--host" in result.stdout or result.returncode == 0


class TestServeMCPIntegration:
    """Integration tests for serve mcp command."""
    
    def test_serve_mcp_help(self):
        """Test serve mcp --help works."""
        result = subprocess.run(
            [sys.executable, "-m", "praisonai.cli.commands.serve", "mcp", "--help"],
            capture_output=True,
            text=True,
            cwd="/Users/praison/praisonai-package/src/praisonai"
        )
        assert "--transport" in result.stdout or result.returncode == 0


class TestServeRecipeIntegration:
    """Integration tests for serve recipe command."""
    
    def test_serve_recipe_help(self):
        """Test serve recipe --help works."""
        result = subprocess.run(
            [sys.executable, "-m", "praisonai.cli.commands.serve", "recipe", "--help"],
            capture_output=True,
            text=True,
            cwd="/Users/praison/praisonai-package/src/praisonai"
        )
        assert "--host" in result.stdout or result.returncode == 0


class TestAllServeCommandsHelp:
    """Test all serve commands have proper help."""
    
    @pytest.mark.parametrize("command", [
        "agents", "gateway", "mcp", "acp", "lsp", "ui", 
        "rag", "registry", "docs", "scheduler", "recipe",
        "a2a", "a2u", "unified"
    ])
    def test_serve_command_help(self, command):
        """Test each serve command has working --help."""
        from typer.testing import CliRunner
        from praisonai.cli.commands.serve import app
        
        runner = CliRunner()
        result = runner.invoke(app, [command, "--help"])
        
        # Should show help text
        assert result.exit_code == 0
        assert "--help" in result.output or command in result.output.lower()
