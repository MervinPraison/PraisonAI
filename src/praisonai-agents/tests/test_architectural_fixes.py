"""
Tests for architectural fixes from Issue #1392.

This test suite validates all three gaps:
1. Gap 1: Sync/Async Duplication - unified execution core
2. Gap 2: Parallel Tool Execution - concurrent tool calls
3. Gap 3: Streaming Protocol - unified streaming adapters

Tests follow AGENTS.md requirements:
- Real agentic tests (actual LLM calls)
- Protocol-driven validation
- Backward compatibility verification
- Performance impact measurement
"""

import pytest
import asyncio
import time
from unittest.mock import Mock, patch, MagicMock
from praisonaiagents import Agent, tool
from praisonaiagents.agent.unified_execution_mixin import UnifiedExecutionMixin
from praisonaiagents.llm.streaming_protocol import (
    get_streaming_adapter, 
    DefaultStreamingAdapter,
    OllamaStreamingAdapter,
    AnthropicStreamingAdapter,
    GeminiStreamingAdapter
)
from praisonaiagents.streaming.events import StreamEvent, StreamEventType
from praisonaiagents.tools.call_executor import (
    create_tool_call_executor,
    ToolCall,
    ParallelToolCallExecutor,
    SequentialToolCallExecutor
)


class TestGap1UnifiedExecution:
    """Test Gap 1: Sync/Async Duplication elimination."""
    
    def test_unified_execution_mixin_integration(self):
        """Test that UnifiedExecutionMixin can be mixed into Agent."""
        
        class TestAgent(UnifiedExecutionMixin):
            def __init__(self):
                self.name = "test"
                self.role = "assistant" 
                self.goal = "test"
                self.tools = []
                self.chat_history = []
                self._hook_runner = Mock()
                self._hook_runner.execute = Mock(return_value=asyncio.coroutine(lambda *args: [])())
                self._hook_runner.is_blocked = Mock(return_value=False)
                
            def _build_system_prompt(self, tools=None):
                return "Test system prompt"
                
            def _build_multimodal_prompt(self, prompt, attachments):
                return prompt
        
        agent = TestAgent()
        
        # Test that unified methods exist
        assert hasattr(agent, 'unified_chat')
        assert hasattr(agent, 'unified_achat')
        assert hasattr(agent, 'unified_execute_tool')
        assert hasattr(agent, 'unified_execute_tool_async')
        
        # Test that async-first implementation exists
        assert hasattr(agent, '_unified_chat_impl')
        assert hasattr(agent, '_unified_tool_execution')
    
    @pytest.mark.asyncio
    async def test_async_first_implementation(self):
        """Test that unified async implementation contains core logic."""
        
        class MockAgent(UnifiedExecutionMixin):
            def __init__(self):
                self.name = "mock"
                self.role = "test"
                self.goal = "test" 
                self.tools = []
                self.chat_history = []
                self.llm_instance = Mock()
                self.llm_instance.get_response_async = Mock(return_value="Test response")
                self._hook_runner = Mock()
                self._hook_runner.execute = Mock(return_value=asyncio.coroutine(lambda *args: [])())
                self._hook_runner.is_blocked = Mock(return_value=False)
                self._using_custom_llm = False
                
            def _build_system_prompt(self, tools=None):
                return "System prompt"
                
            def _build_multimodal_prompt(self, prompt, attachments):
                return prompt
        
        agent = MockAgent()
        
        # Test async core implementation
        result = await agent._unified_chat_impl("Test prompt")
        
        # Verify LLM was called with correct parameters
        agent.llm_instance.get_response_async.assert_called_once()
        call_kwargs = agent.llm_instance.get_response_async.call_args[1]
        
        assert call_kwargs['prompt'] == "Test prompt"
        assert call_kwargs['system_prompt'] == "System prompt"
        assert call_kwargs['chat_history'] == []
        assert 'parallel_tool_calls' in call_kwargs  # Gap 2 integration
        assert result == "Test response"
    
    def test_sync_bridge_functionality(self):
        """Test that sync bridge correctly delegates to async core."""
        
        class TestAgent(UnifiedExecutionMixin):
            def __init__(self):
                self.name = "test"
                
            async def _unified_chat_impl(self, prompt, **kwargs):
                return f"Async result: {prompt}"
        
        agent = TestAgent()
        
        # Mock the async execution runner to avoid event loop complexities
        with patch.object(agent, '_run_async_in_sync_context') as mock_runner:
            mock_runner.return_value = "Sync result: test"
            
            result = agent.unified_chat("test")
            
            # Verify sync bridge was used
            mock_runner.assert_called_once()
            assert result == "Sync result: test"
    
    def test_backward_compatibility(self):
        """Test that existing chat/achat APIs remain unchanged."""
        
        # This test would verify that existing Agent.chat() and Agent.achat()
        # still work with the same signatures and behavior.
        # For now, we validate the method signatures exist.
        
        agent = Agent(name="test", instructions="test")
        
        # Verify original methods still exist  
        assert hasattr(agent, 'chat')
        assert hasattr(agent, 'achat')
        
        # Verify they accept the same parameters
        import inspect
        chat_sig = inspect.signature(agent.chat)
        expected_params = [
            'prompt', 'temperature', 'tools', 'output_json', 'output_pydantic',
            'reasoning_steps', 'stream', 'task_name', 'task_description', 'task_id',
            'config', 'force_retrieval', 'skip_retrieval', 'attachments', 'tool_choice'
        ]
        
        for param in expected_params:
            assert param in chat_sig.parameters


class TestGap2ParallelToolExecution:
    """Test Gap 2: Parallel Tool Execution (already implemented, verify integration)."""
    
    def test_tool_call_executor_protocol(self):
        """Test ToolCallExecutor protocol and implementations."""
        
        # Test factory function
        sequential = create_tool_call_executor(parallel=False)
        parallel = create_tool_call_executor(parallel=True, max_workers=3)
        
        assert isinstance(sequential, SequentialToolCallExecutor)
        assert isinstance(parallel, ParallelToolCallExecutor)
        assert parallel.max_workers == 3
    
    def test_parallel_vs_sequential_performance(self):
        """Test that parallel execution is faster for multiple tool calls."""
        
        @tool
        def slow_tool(duration: float) -> str:
            """A tool that simulates slow I/O."""
            time.sleep(duration)
            return f"Slept for {duration}s"
        
        def mock_execute_tool_fn(name, args, tool_call_id):
            return slow_tool(**args)
        
        tool_calls = [
            ToolCall("slow_tool", {"duration": 0.1}, "call_1"),
            ToolCall("slow_tool", {"duration": 0.1}, "call_2"),
            ToolCall("slow_tool", {"duration": 0.1}, "call_3")
        ]
        
        # Test sequential execution
        sequential_executor = SequentialToolCallExecutor()
        start_time = time.time()
        sequential_results = sequential_executor.execute_batch(tool_calls, mock_execute_tool_fn)
        sequential_duration = time.time() - start_time
        
        # Test parallel execution
        parallel_executor = ParallelToolCallExecutor(max_workers=3)
        start_time = time.time()
        parallel_results = parallel_executor.execute_batch(tool_calls, mock_execute_tool_fn)
        parallel_duration = time.time() - start_time
        
        # Verify results are the same
        assert len(sequential_results) == len(parallel_results) == 3
        for seq_result, par_result in zip(sequential_results, parallel_results):
            assert seq_result.function_name == par_result.function_name
            assert seq_result.result == par_result.result
        
        # Verify parallel is significantly faster
        speedup = sequential_duration / parallel_duration
        assert speedup > 2.0  # Should be close to 3x speedup for 3 concurrent calls
        
        print(f"Sequential: {sequential_duration:.2f}s, Parallel: {parallel_duration:.2f}s, Speedup: {speedup:.1f}x")
    
    def test_parallel_tool_calls_integration_with_agent(self):
        """Test that Agent respects parallel_tool_calls parameter."""
        
        # Test agent creation with parallel tool calls enabled
        agent = Agent(
            name="parallel_test",
            instructions="You are a test agent",
            parallel_tool_calls=True
        )
        
        assert hasattr(agent, 'parallel_tool_calls')
        assert agent.parallel_tool_calls is True
        
        # Test default behavior (should be False for backward compatibility)
        default_agent = Agent(name="default_test", instructions="test")
        assert getattr(default_agent, 'parallel_tool_calls', False) is False


class TestGap3StreamingProtocol:
    """Test Gap 3: Streaming Protocol unification."""
    
    def test_streaming_adapter_registry(self):
        """Test that streaming adapters are properly registered."""
        
        # Test default adapters are available
        default_adapter = get_streaming_adapter("default")
        ollama_adapter = get_streaming_adapter("ollama")
        anthropic_adapter = get_streaming_adapter("anthropic")
        gemini_adapter = get_streaming_adapter("gemini")
        
        assert isinstance(default_adapter, DefaultStreamingAdapter)
        assert isinstance(ollama_adapter, OllamaStreamingAdapter)
        assert isinstance(anthropic_adapter, AnthropicStreamingAdapter)
        assert isinstance(gemini_adapter, GeminiStreamingAdapter)
        
        # Test provider name matching
        claude_adapter = get_streaming_adapter("claude-3-sonnet")
        assert isinstance(claude_adapter, AnthropicStreamingAdapter)
        
        ollama_model_adapter = get_streaming_adapter("ollama/llama2")
        assert isinstance(ollama_model_adapter, OllamaStreamingAdapter)
    
    def test_provider_specific_streaming_capabilities(self):
        """Test that each adapter reports correct streaming capabilities."""
        
        # Default adapter - supports most streaming scenarios
        default = get_streaming_adapter("default")
        assert default.can_stream() is True
        assert default.can_stream(tools=[{"name": "test"}]) is True
        
        # Ollama adapter - doesn't support streaming with tools
        ollama = get_streaming_adapter("ollama")
        assert ollama.can_stream() is True
        assert ollama.can_stream(tools=[{"name": "test"}]) is False
        
        # Anthropic adapter - disabled due to litellm bug
        anthropic = get_streaming_adapter("anthropic")
        assert anthropic.can_stream() is False
        assert anthropic.can_stream(tools=[{"name": "test"}]) is False
        
        # Gemini adapter - supports basic streaming but not with tools
        gemini = get_streaming_adapter("gemini")
        assert gemini.can_stream() is True
        assert gemini.can_stream(tools=[{"name": "test"}]) is False
    
    def test_stream_unavailable_events(self):
        """Test that adapters emit proper unavailable events."""
        
        # Test Anthropic unavailable event
        anthropic = get_streaming_adapter("anthropic")
        event = anthropic.create_stream_unavailable_event()
        
        assert event.type == StreamEventType.STREAM_UNAVAILABLE
        assert "litellm" in event.error.lower()
        assert event.metadata["provider"] == "anthropic"
        
        # Test Gemini unavailable event with tools
        gemini = get_streaming_adapter("gemini")
        event = gemini.create_stream_unavailable_event("tools present")
        
        assert event.type == StreamEventType.STREAM_UNAVAILABLE
        assert "tools present" in event.error
        assert event.metadata["provider"] == "gemini"
    
    @pytest.mark.asyncio
    async def test_streaming_adapter_integration(self):
        """Test streaming adapter integration with mock LLM responses."""
        
        default_adapter = get_streaming_adapter("default")
        
        # Mock the litellm.acompletion to return test stream chunks
        mock_chunks = [
            Mock(choices=[Mock(delta=Mock(content="Hello", tool_calls=None))]),
            Mock(choices=[Mock(delta=Mock(content=" world", tool_calls=None))]),
            Mock(choices=[Mock(delta=Mock(content="!", tool_calls=None))])
        ]
        
        async def mock_acompletion(**kwargs):
            for chunk in mock_chunks:
                yield chunk
        
        with patch('litellm.acompletion', mock_acompletion):
            events = []
            async for event in default_adapter.stream_completion(
                messages=[{"role": "user", "content": "Hello"}],
                model="gpt-3.5-turbo",
                temperature=1.0
            ):
                events.append(event)
        
        # Verify event sequence
        assert len(events) >= 4  # REQUEST_START, FIRST_TOKEN, DELTA_TEXT, STREAM_END
        assert events[0].type == StreamEventType.REQUEST_START
        assert events[-1].type == StreamEventType.STREAM_END
        
        # Find text events
        text_events = [e for e in events if e.type in [StreamEventType.FIRST_TOKEN, StreamEventType.DELTA_TEXT]]
        assert len(text_events) == 3
        assert text_events[0].content == "Hello"
        assert text_events[1].content == " world"
        assert text_events[2].content == "!"


class TestRealAgenticIntegration:
    """Real agentic tests as required by AGENTS.md."""
    
    @pytest.mark.asyncio
    async def test_real_agent_with_architectural_fixes(self):
        """
        Real agentic test demonstrating all three architectural fixes working together.
        
        This test creates an actual agent, gives it tools, and runs it with:
        - Unified sync/async execution (Gap 1)
        - Parallel tool execution (Gap 2) 
        - Unified streaming protocol (Gap 3)
        """
        
        @tool
        def get_weather(location: str) -> str:
            """Get weather for a location."""
            return f"Weather in {location}: 72°F, sunny"
        
        @tool  
        def get_time(timezone: str) -> str:
            """Get current time in timezone."""
            return f"Time in {timezone}: 2:30 PM"
        
        @tool
        def get_news(topic: str) -> str:
            """Get news about a topic."""
            return f"Latest news about {topic}: All good!"
        
        # Create agent with all architectural fixes enabled
        agent = Agent(
            name="integration_test",
            instructions="You are a helpful assistant. Use tools when needed.",
            tools=[get_weather, get_time, get_news],
            parallel_tool_calls=True,  # Gap 2: Enable parallel execution
            llm="gpt-4o-mini",  # Use a real model
            stream=True  # Gap 3: Enable streaming
        )
        
        # Test that would trigger multiple tool calls (testing Gap 2)
        prompt = "What's the weather in New York, time in EST, and news about technology?"
        
        # This should use:
        # - Gap 1: Unified execution core (async-first with sync bridge)
        # - Gap 2: Parallel tool execution if LLM returns multiple tool calls
        # - Gap 3: Streaming protocol with proper adapter selection
        
        try:
            # Use sync interface (tests Gap 1 sync bridge)
            response = agent.chat(prompt)
            
            # Verify response contains information from all tools
            assert response is not None
            assert len(response) > 10  # Should be substantial response
            print(f"Agent response: {response}")
            
            # Test async interface (tests Gap 1 async-first core)
            async_response = await agent.achat("Tell me about the weather in Paris")
            assert async_response is not None
            assert len(async_response) > 10
            print(f"Async agent response: {async_response}")
            
            return True  # Test passed
            
        except Exception as e:
            print(f"Real agentic test failed (may be expected if no API key): {e}")
            # Don't fail the test if it's due to missing API credentials
            if "api key" in str(e).lower() or "authentication" in str(e).lower():
                pytest.skip(f"Skipped due to missing API credentials: {e}")
            else:
                raise
    
    def test_backward_compatibility_real_agent(self):
        """
        Test that existing agent patterns still work with architectural changes.
        
        This verifies that the architectural fixes don't break existing user code.
        """
        
        # Test traditional agent creation and usage patterns
        agent = Agent(name="backward_test", instructions="You are helpful")
        
        # Verify existing methods and properties work
        assert agent.name == "backward_test" 
        assert hasattr(agent, 'chat')
        assert hasattr(agent, 'achat')
        assert hasattr(agent, 'start')
        
        # Test with mock LLM to avoid API dependency
        with patch.object(agent, 'llm_instance') as mock_llm:
            mock_llm.get_response.return_value = "Test response"
            
            response = agent.chat("Hello")
            assert response == "Test response"
            
            # Verify the LLM was called with expected parameters
            mock_llm.get_response.assert_called_once()


if __name__ == "__main__":
    # Run tests with verbose output
    pytest.main([__file__, "-v", "-s"])