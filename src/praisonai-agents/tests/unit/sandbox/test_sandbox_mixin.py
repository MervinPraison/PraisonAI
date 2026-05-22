"""
Unit tests for SandboxMixin functionality.
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch
from praisonaiagents.agent.sandbox_mixin import SandboxMixin
from praisonaiagents.sandbox import SandboxConfig, SandboxResult, SandboxStatus


class MockAgent(SandboxMixin):
    """Mock agent class for testing SandboxMixin."""
    
    def __init__(self, sandbox=None, verbose=False):
        super().__init__(sandbox=sandbox)
        self.verbose = verbose


class TestSandboxMixin:
    """Test SandboxMixin functionality."""

    def test_init_no_sandbox(self):
        """Test initialization without sandbox."""
        agent = MockAgent()
        assert not agent.has_sandbox
        assert agent.sandbox_config is None

    def test_init_with_boolean_true(self):
        """Test initialization with sandbox=True."""
        agent = MockAgent(sandbox=True)
        assert agent.has_sandbox
        assert agent.sandbox_config is not None
        assert agent.sandbox_config.sandbox_type == "subprocess"

    def test_init_with_config(self):
        """Test initialization with explicit config."""
        config = SandboxConfig.docker("python:3.11")
        agent = MockAgent(sandbox=config)
        assert agent.has_sandbox
        assert agent.sandbox_config == config

    def test_get_sandbox_manager_no_config(self):
        """Test get_sandbox_manager without config."""
        agent = MockAgent()
        manager = agent.get_sandbox_manager()
        assert manager is None

    @patch('praisonaiagents.agent.sandbox_mixin.SandboxManager')
    def test_get_sandbox_manager_with_config(self, mock_manager_class):
        """Test get_sandbox_manager with config."""
        config = SandboxConfig.subprocess()
        agent = MockAgent(sandbox=config)
        
        manager = agent.get_sandbox_manager()
        
        mock_manager_class.assert_called_once_with(config)
        assert agent._sandbox_manager is not None

    def test_execute_code_without_sandbox_raises(self):
        """Test that execute_code raises without sandbox."""
        agent = MockAgent()
        
        with pytest.raises(RuntimeError, match="No sandbox configured"):
            agent.execute_code_sync("print('hello')")

    @patch('praisonaiagents.agent.sandbox_mixin.check_code_safety')
    @patch('praisonaiagents.agent.sandbox_mixin.SandboxManager')
    async def test_execute_code_with_warnings(self, mock_manager_class, mock_check_safety):
        """Test execute_code with security warnings."""
        # Setup
        config = SandboxConfig.subprocess()
        agent = MockAgent(sandbox=config, verbose=True)
        
        mock_warnings = ["Potential security issue"]
        mock_check_safety.return_value = mock_warnings
        
        mock_manager = AsyncMock()
        mock_result = SandboxResult(status=SandboxStatus.COMPLETED, stdout="output")
        mock_manager.run_code.return_value = mock_result
        mock_manager_class.return_value = mock_manager
        
        # Execute
        result = await agent.execute_code("print('test')", check_security=True)
        
        # Verify
        mock_check_safety.assert_called_once_with("print('test')", "python")
        mock_manager.run_code.assert_called_once()
        assert result == mock_result

    @patch('praisonaiagents.agent.sandbox_mixin.SandboxManager')
    async def test_run_shell_command(self, mock_manager_class):
        """Test run_shell_command functionality."""
        config = SandboxConfig.subprocess()
        agent = MockAgent(sandbox=config)
        
        # Mock manager as async context manager
        mock_manager = AsyncMock()
        mock_result = SandboxResult(status=SandboxStatus.COMPLETED, stdout="result")
        mock_manager.__aenter__.return_value = mock_manager
        mock_manager.__aexit__.return_value = None
        mock_manager.run_command.return_value = mock_result
        
        mock_manager_class.return_value = mock_manager
        
        result = await agent.run_shell_command("echo hello")
        
        mock_manager.run_command.assert_called_once_with("echo hello")
        assert result == mock_result

    def test_get_sandbox_status_no_config(self):
        """Test get_sandbox_status without config."""
        agent = MockAgent()
        status = agent.get_sandbox_status()
        assert status == {"configured": False}

    @patch('praisonaiagents.agent.sandbox_mixin.SandboxManager')
    def test_get_sandbox_status_with_config(self, mock_manager_class):
        """Test get_sandbox_status with config."""
        config = SandboxConfig.subprocess()
        agent = MockAgent(sandbox=config)
        
        mock_manager = Mock()
        mock_manager.get_available_types.return_value = {"subprocess": True}
        mock_manager_class.return_value = mock_manager
        
        status = agent.get_sandbox_status()
        
        assert status["configured"] is True
        assert status["config"] is not None
        assert status["available_types"] == {"subprocess": True}
        assert status["current_type"] == "subprocess"

    def test_get_code_execution_tools_no_sandbox(self):
        """Test _get_code_execution_tools without sandbox."""
        agent = MockAgent()
        tools = agent._get_code_execution_tools()
        assert tools == []

    @patch('praisonaiagents.agent.sandbox_mixin.SandboxManager')
    def test_get_code_execution_tools_with_sandbox(self, mock_manager_class):
        """Test _get_code_execution_tools with sandbox."""
        config = SandboxConfig.subprocess()
        agent = MockAgent(sandbox=config)
        
        tools = agent._get_code_execution_tools()
        
        assert len(tools) == 2
        # Check that tools are functions
        assert callable(tools[0])
        assert callable(tools[1])

    async def test_sandbox_cleanup(self):
        """Test sandbox cleanup functionality."""
        agent = MockAgent()
        
        # Mock manager
        mock_manager = AsyncMock()
        agent._sandbox_manager = mock_manager
        
        await agent.sandbox_cleanup()
        
        mock_manager.__aexit__.assert_called_once_with(None, None, None)
        assert agent._sandbox_manager is None

    async def test_sandbox_cleanup_with_error(self):
        """Test sandbox cleanup with error handling."""
        agent = MockAgent()
        
        # Mock manager that raises exception
        mock_manager = AsyncMock()
        mock_manager.__aexit__.side_effect = Exception("Cleanup failed")
        agent._sandbox_manager = mock_manager
        
        # Should not raise, just log warning
        await agent.sandbox_cleanup()
        
        assert agent._sandbox_manager is None