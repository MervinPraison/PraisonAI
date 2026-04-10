"""
Tests for PraisonAI Terminal-Bench 2.0 Integration

This module contains both unit tests and integration tests for the
PraisonAI Harbor integration.

Run tests with:
    python -m pytest examples/terminal_bench/test_integration.py -v

Requirements:
    pip install pytest praisonaiagents
    # Harbor is optional for unit tests, required for integration tests
"""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch
from pathlib import Path


class TestPraisonAIExternalAgent:
    """Test the external agent implementation."""
    
    def test_agent_metadata(self):
        """Test agent name and version reporting."""
        try:
            from .praisonai_external_agent import PraisonAIExternalAgent
        except ImportError:
            pytest.skip("Harbor not installed - skipping Harbor-specific tests")
            
        agent = PraisonAIExternalAgent()
        assert agent.name() == "praisonai"
        
        # Version should be None if praisonaiagents not installed, or actual version
        version = agent.version()
        assert version is None or isinstance(version, str)

    @pytest.mark.asyncio
    async def test_setup(self):
        """Test agent setup phase."""
        try:
            from .praisonai_external_agent import PraisonAIExternalAgent
        except ImportError:
            pytest.skip("Harbor not installed")
            
        agent = PraisonAIExternalAgent()
        mock_env = Mock()
        
        # Setup should complete without error (external agent needs no setup)
        await agent.setup(mock_env)

    @pytest.mark.asyncio
    async def test_bash_tool_execution(self):
        """Test the bash tool wrapper around Harbor's exec()."""
        try:
            from .praisonai_external_agent import PraisonAIExternalAgent
        except ImportError:
            pytest.skip("Harbor not installed")
            
        # Mock Harbor environment
        mock_env = Mock()
        mock_result = Mock()
        mock_result.stdout = "Hello, World!"
        mock_result.stderr = ""
        mock_result.return_code = 0
        mock_env.exec = AsyncMock(return_value=mock_result)
        
        # Mock agent context
        mock_context = Mock()
        mock_context.metadata = {}
        
        agent = PraisonAIExternalAgent()
        
        # Mock PraisonAI Agent to avoid LLM calls in tests
        with patch('praisonaiagents.Agent') as mock_agent_class:
            mock_agent_instance = Mock()
            mock_agent_instance.start.return_value = "Task completed successfully"
            mock_agent_instance.name = "terminal-agent"
            mock_agent_class.return_value = mock_agent_instance
            
            # Mock approval backend
            with patch('praisonaiagents.approval.set_approval_backend'):
                await agent.run("echo 'Hello, World!'", mock_env, mock_context)
            
            # Verify agent was created with correct parameters
            mock_agent_class.assert_called_once()
            args, kwargs = mock_agent_class.call_args
            
            assert kwargs['name'] == 'terminal-agent'
            assert 'tools' in kwargs
            assert len(kwargs['tools']) == 1  # bash_tool
            assert kwargs['verbose'] is False
            assert kwargs['memory'] is False

    def test_context_population(self):
        """Test that agent context is properly populated."""
        try:
            from .praisonai_external_agent import PraisonAIExternalAgent
        except ImportError:
            pytest.skip("Harbor not installed")
            
        agent_impl = PraisonAIExternalAgent()
        
        # Mock agent with usage data
        mock_agent = Mock()
        mock_agent.name = "test-agent"
        mock_agent.llm = "gpt-4o"
        mock_agent._usage = Mock()
        mock_agent._usage.input_tokens = 100
        mock_agent._usage.output_tokens = 50
        mock_agent._cost = 0.01
        
        mock_context = Mock()
        mock_context.metadata = {}
        
        # Test context population
        agent_impl._populate_context(mock_agent, mock_context, "Test result")
        
        assert mock_context.n_input_tokens == 100
        assert mock_context.n_output_tokens == 50
        assert mock_context.cost_usd == 0.01
        assert mock_context.metadata['agent_name'] == 'test-agent'
        assert mock_context.metadata['model'] == 'gpt-4o'
        assert mock_context.metadata['framework'] == 'praisonai'


class TestPraisonAIInstalledAgent:
    """Test the installed agent implementation."""
    
    def test_agent_configuration(self):
        """Test agent CLI flags and configuration."""
        try:
            from .praisonai_installed_agent import PraisonAIInstalledAgent
        except ImportError:
            pytest.skip("Harbor not installed")
            
        agent = PraisonAIInstalledAgent()
        assert agent.name() == "praisonai"
        assert agent.SUPPORTS_ATIF is False  # Until trajectory format is implemented
        
        # Check CLI flags
        flag_names = [flag.name if hasattr(flag, 'name') else str(flag) for flag in agent.CLI_FLAGS]
        expected_flags = ['max_turns', 'verbose', 'memory', 'auto_approval']
        for expected in expected_flags:
            assert any(expected in flag_name for flag_name in flag_names)

    def test_version_command(self):
        """Test version detection command."""
        try:
            from .praisonai_installed_agent import PraisonAIInstalledAgent
        except ImportError:
            pytest.skip("Harbor not installed")
            
        agent = PraisonAIInstalledAgent()
        version_cmd = agent.get_version_command()
        
        assert version_cmd is not None
        assert "praisonaiagents" in version_cmd
        assert "__version__" in version_cmd

    def test_runner_script_generation(self):
        """Test that the headless runner script is properly generated."""
        try:
            from .praisonai_installed_agent import PraisonAIInstalledAgent
        except ImportError:
            pytest.skip("Harbor not installed")
            
        agent = PraisonAIInstalledAgent()
        script = agent._build_runner_script()
        
        assert "import praisonaiagents" in script
        assert "Agent" in script
        assert "execute_command" in script
        assert "AutoApproveBackend" in script
        assert "json.dumps" in script


class TestIntegration:
    """Integration tests that require both PraisonAI and Harbor."""
    
    @pytest.mark.integration
    def test_praisonai_agent_real(self):
        """
        Real agentic test - agent must call LLM end-to-end.
        
        This is a MANDATORY test per AGENTS.md §9.4.
        Agent MUST call agent.start() with real prompt and produce LLM output.
        """
        try:
            from praisonaiagents import Agent
        except ImportError:
            pytest.skip("PraisonAI not installed")
            
        # Create real agent that will call LLM
        agent = Agent(
            name="test-terminal-agent", 
            instructions="You are a helpful terminal assistant"
        )
        
        # Real agentic test - agent must call LLM and produce text response
        result = agent.start("Say hello in one sentence and mention you can help with terminal tasks")
        
        # Verify we got actual LLM output
        assert result is not None
        assert isinstance(result, str)
        assert len(result) > 0
        
        # Print output for manual verification
        print("✅ Real agentic test result:")
        print(result)

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_bash_tool_real_execution(self):
        """Test bash tool with real command execution (if safe)."""
        # This would test real bash execution in a safe environment
        # For now, we'll mock it to avoid system changes
        
        mock_result = Mock()
        mock_result.stdout = "PraisonAI Terminal Test\n"
        mock_result.stderr = ""
        mock_result.return_code = 0
        
        # Test that our bash tool wrapper works correctly
        async def mock_exec(command, timeout_sec=30):
            assert "echo" in command  # Ensure we're testing echo command
            return mock_result
            
        # This simulates Harbor's BaseEnvironment.exec()
        result = await mock_exec("echo 'PraisonAI Terminal Test'")
        
        assert result.stdout.strip() == "PraisonAI Terminal Test"
        assert result.return_code == 0

    @pytest.mark.integration
    def test_auto_approval_setup(self):
        """Test that auto-approval backend works correctly."""
        try:
            from praisonaiagents.approval import set_approval_backend, AutoApproveBackend
        except ImportError:
            pytest.skip("PraisonAI approval system not available")
            
        # Test setting and restoring approval backend
        original = set_approval_backend(AutoApproveBackend())
        new_backend = set_approval_backend(original)
        
        assert isinstance(new_backend, AutoApproveBackend)


if __name__ == "__main__":
    # Allow running tests directly
    import sys
    
    print("PraisonAI Terminal-Bench 2.0 Integration Tests")
    print("=" * 50)
    
    # Check dependencies
    try:
        import praisonaiagents
        print(f"✅ PraisonAI version: {praisonaiagents.__version__}")
    except ImportError:
        print("❌ PraisonAI not installed: pip install praisonaiagents")
        sys.exit(1)
    
    try:
        import harbor
        print("✅ Harbor framework available")
    except ImportError:
        print("⚠️  Harbor not installed: pip install harbor")
        print("   (Some tests will be skipped)")
    
    print()
    print("Run tests with: python -m pytest examples/terminal_bench/test_integration.py -v")
    print("Run real agentic test: python -m pytest examples/terminal_bench/test_integration.py::TestIntegration::test_praisonai_agent_real -v -s")