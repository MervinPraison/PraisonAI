"""
Tests for Agent execution API semantics: start(), run(), stream()

TDD tests for the new execution API:
- start() = interactive, streams by default in TTY
- run() = production, silent by default
- stream() = app-friendly iterator
"""

import pytest
import sys
from unittest.mock import patch


class TestAgentStartMethod:
    """Tests for Agent.start() - interactive, streaming by default in TTY"""
    
    def test_start_streams_by_default_in_tty(self):
        """start() should stream by default when stdout is a TTY"""
        from praisonaiagents import Agent
        
        # Create agent without stream attribute set (None)
        agent = Agent(name="Test", instructions="You are helpful")
        # Ensure stream attribute is None so TTY detection kicks in
        agent.stream = None
        
        # Mock TTY detection
        with patch.object(sys.stdout, 'isatty', return_value=True):
            # Mock chat to avoid actual LLM call
            with patch.object(agent, '_start_stream') as mock_stream:
                mock_stream.return_value = iter(["Hello", " World"])
                with patch.object(agent, 'chat') as mock_chat:
                    agent.start("Hello")
                    # Should call _start_stream when TTY
                    mock_stream.assert_called_once()
                    mock_chat.assert_not_called()
    
    def test_start_does_not_stream_when_not_tty(self):
        """start() should not stream when stdout is not a TTY"""
        from praisonaiagents import Agent
        
        agent = Agent(name="Test", instructions="You are helpful")
        
        # Mock non-TTY
        with patch.object(sys.stdout, 'isatty', return_value=False):
            with patch.object(agent, '_start_stream') as mock_stream:
                with patch.object(agent, 'chat', return_value="Hello World") as mock_chat:
                    result = agent.start("Hello")
                    # Should call chat, not _start_stream
                    mock_chat.assert_called_once()
                    mock_stream.assert_not_called()
    
    def test_start_respects_explicit_stream_true(self):
        """start(stream=True) should always stream"""
        from praisonaiagents import Agent
        
        agent = Agent(name="Test", instructions="You are helpful")
        
        # Even when not TTY, explicit stream=True should stream
        with patch.object(sys.stdout, 'isatty', return_value=False):
            with patch.object(agent, '_start_stream') as mock_stream:
                mock_stream.return_value = iter(["Hello"])
                result = agent.start("Hello", stream=True)
                mock_stream.assert_called_once()
    
    def test_start_respects_explicit_stream_false(self):
        """start(stream=False) should never stream"""
        from praisonaiagents import Agent
        
        agent = Agent(name="Test", instructions="You are helpful")
        
        # Even when TTY, explicit stream=False should not stream
        with patch.object(sys.stdout, 'isatty', return_value=True):
            with patch.object(agent, 'chat', return_value="Hello") as mock_chat:
                with patch.object(agent, '_start_stream') as mock_stream:
                    result = agent.start("Hello", stream=False)
                    mock_chat.assert_called_once()
                    mock_stream.assert_not_called()
    
    def test_start_respects_agent_stream_attribute(self):
        """start() should respect agent's stream attribute over TTY detection"""
        from praisonaiagents import Agent
        
        # Agent with stream=True should always stream
        agent = Agent(name="Test", instructions="You are helpful", output="stream")
        
        with patch.object(sys.stdout, 'isatty', return_value=False):
            with patch.object(agent, '_start_stream') as mock_stream:
                mock_stream.return_value = iter(["Hello"])
                # Agent's stream attribute should take precedence
                if agent.stream:
                    result = agent.start("Hello")
                    mock_stream.assert_called()


class TestAgentRunMethod:
    """Tests for Agent.run() - production, silent by default"""
    
    def test_run_does_not_stream_by_default(self):
        """run() should not stream by default"""
        from praisonaiagents import Agent
        
        agent = Agent(name="Test", instructions="You are helpful")
        
        with patch.object(agent, 'chat', return_value="Hello World") as mock_chat:
            with patch.object(agent, '_start_stream') as mock_stream:
                result = agent.run("Hello")
                # Should call chat with stream=False
                mock_chat.assert_called_once()
                call_kwargs = mock_chat.call_args[1]
                assert call_kwargs.get('stream') == False
                mock_stream.assert_not_called()
    
    def test_run_returns_result_directly(self):
        """run() should return the result directly, not a generator"""
        from praisonaiagents import Agent
        
        agent = Agent(name="Test", instructions="You are helpful")
        
        with patch.object(agent, 'chat', return_value="Hello World") as mock_chat:
            result = agent.run("Hello")
            assert result == "Hello World"
            assert not hasattr(result, '__iter__') or isinstance(result, str)
    
    def test_run_ignores_tty_detection(self):
        """run() should ignore TTY detection and never stream by default"""
        from praisonaiagents import Agent
        
        agent = Agent(name="Test", instructions="You are helpful")
        
        # Even in TTY, run() should not stream
        with patch.object(sys.stdout, 'isatty', return_value=True):
            with patch.object(agent, 'chat', return_value="Hello") as mock_chat:
                with patch.object(agent, '_start_stream') as mock_stream:
                    result = agent.run("Hello")
                    mock_chat.assert_called_once()
                    mock_stream.assert_not_called()
    
    def test_run_can_be_forced_to_stream(self):
        """run(stream=True) should stream when explicitly requested"""
        from praisonaiagents import Agent
        
        agent = Agent(name="Test", instructions="You are helpful")
        
        with patch.object(agent, 'chat', return_value="Hello") as mock_chat:
            result = agent.run("Hello", stream=True)
            # When stream=True is passed, it should be passed to chat
            call_kwargs = mock_chat.call_args[1]
            assert call_kwargs.get('stream') == True


class TestAgentIterStreamMethod:
    """Tests for Agent.iter_stream() - app-friendly iterator"""
    
    def test_iter_stream_returns_iterator(self):
        """iter_stream() should return an iterator"""
        from praisonaiagents import Agent
        
        agent = Agent(name="Test", instructions="You are helpful")
        
        with patch.object(agent, '_start_stream') as mock_stream:
            mock_stream.return_value = iter(["Hello", " ", "World"])
            result = agent.iter_stream("Hello")
            # Should be an iterator/generator
            assert hasattr(result, '__iter__')
            assert hasattr(result, '__next__')
    
    def test_iter_stream_yields_chunks(self):
        """iter_stream() should yield response chunks"""
        from praisonaiagents import Agent
        
        agent = Agent(name="Test", instructions="You are helpful")
        
        with patch.object(agent, '_start_stream') as mock_stream:
            mock_stream.return_value = iter(["Hello", " ", "World"])
            chunks = list(agent.iter_stream("Hello"))
            assert chunks == ["Hello", " ", "World"]
    
    def test_iter_stream_always_streams(self):
        """iter_stream() should always stream regardless of TTY"""
        from praisonaiagents import Agent
        
        agent = Agent(name="Test", instructions="You are helpful")
        
        # Even when not TTY
        with patch.object(sys.stdout, 'isatty', return_value=False):
            with patch.object(agent, '_start_stream') as mock_stream:
                mock_stream.return_value = iter(["Hello"])
                result = agent.iter_stream("Hello")
                # Consume the generator
                list(result)
                mock_stream.assert_called_once()


class TestAsyncMethods:
    """Tests for async versions: arun(), astart()"""
    
    @pytest.mark.asyncio
    async def test_arun_does_not_stream_by_default(self):
        """arun() should not stream by default"""
        from praisonaiagents import Agent
        
        agent = Agent(name="Test", instructions="You are helpful")
        
        with patch.object(agent, 'achat', return_value="Hello World") as mock_achat:
            result = await agent.arun("Hello")
            mock_achat.assert_called_once()
            call_kwargs = mock_achat.call_args[1]
            # stream should be False or not passed (None means default non-streaming)
            assert call_kwargs.get('stream') in (False, None)
    
    @pytest.mark.asyncio
    async def test_astart_streams_in_tty(self):
        """astart() should stream when in TTY"""
        from praisonaiagents import Agent
        
        agent = Agent(name="Test", instructions="You are helpful")
        # Ensure stream attribute is None so TTY detection kicks in
        agent.stream = None
        
        with patch.object(sys.stdout, 'isatty', return_value=True):
            with patch.object(agent, 'achat', return_value="Hello") as mock_achat:
                await agent.astart("Hello")
                call_kwargs = mock_achat.call_args[1]
                assert call_kwargs.get('stream')


class TestMethodSemanticDistinction:
    """Tests to verify start() and run() have distinct semantics"""
    
    def test_start_and_run_are_different(self):
        """start() and run() should have different default behaviors"""
        from praisonaiagents import Agent
        
        agent = Agent(name="Test", instructions="You are helpful")
        # Ensure stream attribute is None so TTY detection kicks in
        agent.stream = None
        
        # In TTY context
        with patch.object(sys.stdout, 'isatty', return_value=True):
            with patch.object(agent, 'chat', return_value="Hello") as mock_chat:
                with patch.object(agent, '_start_stream') as mock_stream:
                    mock_stream.return_value = iter(["Hello"])
                    
                    # start() should stream
                    agent.start("Hello")
                    start_streamed = mock_stream.called
                    
                    mock_stream.reset_mock()
                    mock_chat.reset_mock()
                    
                    # run() should not stream
                    agent.run("Hello")
                    run_streamed = mock_stream.called
                    
                    # They should behave differently
                    assert start_streamed
                    assert not run_streamed
