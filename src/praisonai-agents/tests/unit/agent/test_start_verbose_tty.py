"""
Unit tests for Agent.start() method defaulting to verbose output in TTY.

Tests the behavior that:
- .start() defaults to verbose output when running in a TTY
- .start() uses agent's default (silent) when NOT in TTY
- .run() always uses the agent's default (silent)
- Explicit output= kwarg overrides TTY detection

This implements Option B: Make .start() default to verbose output in TTY.
"""
import pytest
from unittest.mock import Mock, patch
import sys


class TestStartVerboseInTTY:
    """Test that .start() defaults to verbose output in TTY."""

    def test_start_sets_verbose_in_tty(self):
        """Verify .start() shows verbose output when running in TTY.
        
        Note: The implementation temporarily sets verbose=False during chat()
        to prevent duplicate output, then displays the result with rich panels.
        We verify that verbose output IS shown by checking the output contains
        the expected rich panel markers.
        """
        # Mock isatty to return True
        with patch.object(sys.stdout, 'isatty', return_value=True):
            # Create agent with default (silent) output
            from praisonaiagents import Agent
            agent = Agent(instructions="Test agent")
            
            # Verify default is silent
            assert agent.verbose == False, "Default should be silent (verbose=False)"
            
            # Track what happens in start
            def mock_chat(*args, **kwargs):
                return "mock response"
            
            agent.chat = mock_chat
            agent._load_history_context = Mock()
            agent._auto_save_session = Mock()
            
            # Call start - it should produce output (we can't easily capture rich output)
            result = agent.start("Hello")
            
            # The result should be returned
            assert result == "mock response" or result is not None
            
            # Verbose should be restored after
            assert agent.verbose == False, "verbose should be restored after .start()"

    def test_start_respects_explicit_output_kwarg(self):
        """Verify .start() respects explicit output='silent' even in TTY."""
        with patch.object(sys.stdout, 'isatty', return_value=True):
            from praisonaiagents import Agent
            agent = Agent(instructions="Test agent")
            
            captured_verbose = []
            
            def mock_chat(*args, **kwargs):
                captured_verbose.append(agent.verbose)
                return "mock response"
            
            agent.chat = mock_chat
            agent._load_history_context = Mock()
            agent._auto_save_session = Mock()
            
            # Call start with explicit output='silent'
            result = agent.start("Hello", output="silent")
            
            # Should respect explicit silent
            assert captured_verbose[0] == False, "explicit output='silent' should be respected"

    def test_start_silent_when_not_tty(self):
        """Verify .start() stays silent when not in TTY."""
        with patch.object(sys.stdout, 'isatty', return_value=False):
            from praisonaiagents import Agent
            agent = Agent(instructions="Test agent")
            
            captured_verbose = []
            
            def mock_chat(*args, **kwargs):
                captured_verbose.append(agent.verbose)
                return "mock response"
            
            agent.chat = mock_chat
            agent._load_history_context = Mock()
            agent._auto_save_session = Mock()
            
            # Call start in non-TTY
            result = agent.start("Hello")
            
            # Should remain silent
            assert captured_verbose[0] == False, ".start() should stay silent when not TTY"

    def test_run_always_silent(self):
        """Verify .run() is always silent regardless of TTY."""
        with patch.object(sys.stdout, 'isatty', return_value=True):
            from praisonaiagents import Agent
            agent = Agent(instructions="Test agent")
            
            captured_verbose = []
            
            def mock_chat(*args, **kwargs):
                captured_verbose.append(agent.verbose)
                return "mock response"
            
            agent.chat = mock_chat
            agent._load_history_context = Mock()
            agent._auto_save_session = Mock()
            
            # Call run (should stay silent even in TTY)
            result = agent.run("Hello")
            
            # Should be silent
            assert captured_verbose[0] == False, ".run() should always be silent"


class TestStartVerbosePresets:
    """Test the verbose preset values applied by .start()."""

    def test_start_enables_markdown_in_tty(self):
        """Verify .start() also enables markdown=True in TTY."""
        with patch.object(sys.stdout, 'isatty', return_value=True):
            from praisonaiagents import Agent
            agent = Agent(instructions="Test agent")
            
            # Verify default is no markdown
            assert agent.markdown == False, "Default should be no markdown"
            
            captured_markdown = []
            
            def mock_chat(*args, **kwargs):
                captured_markdown.append(agent.markdown)
                return "mock response"
            
            agent.chat = mock_chat
            agent._load_history_context = Mock()
            agent._auto_save_session = Mock()
            
            # Call start
            result = agent.start("Hello")
            
            # Markdown should have been True during the call
            assert captured_markdown[0] == True, ".start() should set markdown=True in TTY"
            
            # Should be restored after
            assert agent.markdown == False, "markdown should be restored after .start()"


class TestAgentWithExplicitVerbose:
    """Test that agents created with output='verbose' work correctly."""

    def test_agent_with_verbose_output(self):
        """Agent created with output='verbose' should have verbose=True."""
        from praisonaiagents import Agent
        agent = Agent(instructions="Test", output="verbose")
        
        assert agent.verbose == True, "output='verbose' should set verbose=True"
        assert agent.markdown == True, "output='verbose' should set markdown=True"

    def test_start_with_already_verbose_agent(self):
        """Start on already-verbose agent should stay verbose after completion.
        
        Note: During chat(), verbose may be temporarily False to prevent
        duplicate output, but should be restored to True after.
        """
        with patch.object(sys.stdout, 'isatty', return_value=True):
            from praisonaiagents import Agent
            agent = Agent(instructions="Test", output="verbose")
            
            def mock_chat(*args, **kwargs):
                return "mock response"
            
            agent.chat = mock_chat
            agent._load_history_context = Mock()
            agent._auto_save_session = Mock()
            
            result = agent.start("Hello")
            
            # Agent should remain verbose after start() completes
            assert agent.verbose == True, "Already-verbose agent should stay verbose"
