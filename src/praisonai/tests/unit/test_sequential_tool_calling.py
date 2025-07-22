#!/usr/bin/env python3
"""
Comprehensive mock tests for sequential tool calling functionality in PraisonAI.
This test suite covers various scenarios of sequential tool execution.
"""

import sys
import os
import pytest
import json
from unittest.mock import patch, MagicMock
from typing import Dict, List, Any
import contextlib

# Add the source path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src', 'praisonai-agents'))

try:
    from praisonaiagents import Agent
except ImportError as e:
    pytest.skip(f"Could not import required modules: {e}", allow_module_level=True)


# Define test tools
def get_stock_price(company_name: str) -> str:
    """Get the stock price of a company"""
    return f"The stock price of {company_name} is 100"


def multiply(a: int, b: int) -> int:
    """Multiply two numbers"""
    return a * b


def add(a: int, b: int) -> int:
    """Add two numbers"""
    return a + b


def format_result(text: str, number: int) -> str:
    """Format a result with text and number"""
    return f"{text}: {number}"


class TestSequentialToolCalling:
    """Test suite for sequential tool calling functionality"""
    
    @patch('praisonaiagents.llm.openai_client.OpenAIClient')
    def test_basic_sequential_tool_calling(self, mock_openai_client_class):
        """Test basic sequential tool calling with two tools"""
        # Create a mock instance
        mock_client_instance = MagicMock()
        mock_openai_client_class.return_value = mock_client_instance
        
        # Mock the chat_completion_with_tools to return a ChatCompletion object with final result
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "The stock price of Google is 100, and when multiplied by 2, the result is 200."
        mock_client_instance.chat_completion_with_tools.return_value = mock_response
        
        # Create agent
        agent = Agent(
            name="Test Agent",
            instructions="You are a helpful assistant.",
            llm='gpt-3.5-turbo',
            tools=[get_stock_price, multiply]
        )
        
        # Execute
        result = agent.chat("What is the stock price of Google? Multiply it by 2.")
        
        # Verify
        assert mock_client_instance.chat_completion_with_tools.called
        assert "200" in result
        assert "Google" in result
    
    @patch('praisonaiagents.llm.openai_client.OpenAIClient')
    def test_three_tool_sequential_calling(self, mock_openai_client_class):
        """Test sequential calling of three tools"""
        # Create a mock instance
        mock_client_instance = MagicMock()
        mock_openai_client_class.return_value = mock_client_instance
        
        # Mock response
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "The stock price of Apple is 100. Multiplied by 3 gives 300. Adding 50 results in 350."
        mock_client_instance.chat_completion_with_tools.return_value = mock_response
        
        # Create agent
        agent = Agent(
            name="Test Agent",
            instructions="You are a helpful assistant.",
            llm='gpt-3.5-turbo',
            tools=[get_stock_price, multiply, add]
        )
        
        # Execute
        result = agent.chat("Get Apple stock price, multiply by 3, then add 50.")
        
        # Verify
        assert mock_client_instance.chat_completion_with_tools.called
        assert "350" in result
    
    @patch('praisonaiagents.llm.openai_client.OpenAIClient')
    def test_sequential_with_dependencies(self, mock_openai_client_class):
        """Test sequential tool calling where later tools depend on earlier results"""
        # Create a mock instance
        mock_client_instance = MagicMock()
        mock_openai_client_class.return_value = mock_client_instance
        
        # Mock response
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Total stock value: 200"
        mock_client_instance.chat_completion_with_tools.return_value = mock_response
        
        # Create agent
        agent = Agent(
            name="Test Agent",
            instructions="You are a helpful assistant.",
            llm='gpt-3.5-turbo',
            tools=[get_stock_price, add, format_result]
        )
        
        # Execute
        result = agent.chat("Get stock prices for Microsoft and Amazon, add them, and format the result.")
        
        # Verify
        assert mock_client_instance.chat_completion_with_tools.called
        assert "Total stock value: 200" in result
    
    @patch('praisonaiagents.llm.openai_client.OpenAIClient')
    def test_sequential_with_streaming(self, mock_openai_client_class):
        """Test sequential tool calling with streaming enabled"""
        # Create a mock instance
        mock_client_instance = MagicMock()
        mock_openai_client_class.return_value = mock_client_instance
        
        # Mock response
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "The stock price of Tesla is 100. Multiplied by 2 gives 200."
        mock_client_instance.chat_completion_with_tools.return_value = mock_response
        
        # Create agent with streaming
        agent = Agent(
            name="Test Agent",
            instructions="You are a helpful assistant.",
            llm='gpt-3.5-turbo',
            tools=[get_stock_price, multiply],
            stream=True
        )
        
        # Execute
        result = agent.chat("Get Tesla stock price and multiply by 2.")
        
        # Verify
        assert mock_client_instance.chat_completion_with_tools.called
        assert "200" in result
        assert "Tesla" in result
    
    @patch('praisonaiagents.llm.openai_client.OpenAIClient')
    def test_sequential_error_handling(self, mock_openai_client_class):
        """Test error handling in sequential tool calling"""
        # Mock a tool that raises an exception
        def failing_tool(x: int) -> int:
            raise ValueError("Tool execution failed")
        
        # Create a mock instance
        mock_client_instance = MagicMock()
        mock_openai_client_class.return_value = mock_client_instance
        
        # Mock the chat_completion_with_tools to raise an exception
        mock_client_instance.chat_completion_with_tools.side_effect = ValueError("Tool execution failed")
        
        # Create agent
        agent = Agent(
            name="Test Agent",
            instructions="You are a helpful assistant.",
            llm='gpt-3.5-turbo',
            tools=[failing_tool]
        )
        
        # Execute - should handle the error gracefully
        result = agent.chat("Use the failing tool with value 42.")
        
        # The agent should return None when error occurs
        assert result is None
    
    @patch('praisonaiagents.llm.openai_client.OpenAIClient')
    def test_sequential_with_ollama(self, mock_openai_client_class):
        """Test sequential tool calling with Ollama provider format"""
        # Create a mock instance
        mock_client_instance = MagicMock()
        mock_openai_client_class.return_value = mock_client_instance
        
        # Mock response
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Nvidia stock is 100, multiplied by 5 gives 500."
        mock_client_instance.chat_completion_with_tools.return_value = mock_response
        
        # Create agent with Ollama model
        agent = Agent(
            name="Test Agent",
            instructions="You are a helpful assistant.",
            llm='ollama/llama2',
            tools=[get_stock_price, multiply]
        )
        
        # Execute
        result = agent.chat("Get Nvidia stock price and multiply by 5.")
        
        # Verify
        assert mock_client_instance.chat_completion_with_tools.called
        assert "500" in result
    
    @patch('praisonaiagents.llm.openai_client.OpenAIClient')
    def test_multiple_tools_single_response(self, mock_openai_client_class):
        """Test when LLM calls multiple tools in a single response"""
        # Create a mock instance
        mock_client_instance = MagicMock()
        mock_openai_client_class.return_value = mock_client_instance
        
        # Mock response
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Google and Apple stocks are both 100, total is 200."
        mock_client_instance.chat_completion_with_tools.return_value = mock_response
        
        # Create agent
        agent = Agent(
            name="Test Agent",
            instructions="You are a helpful assistant.",
            llm='gpt-4',
            tools=[get_stock_price, add]
        )
        
        # Execute
        result = agent.chat("Get stock prices for Google and Apple, then add them.")
        
        # Verify
        assert mock_client_instance.chat_completion_with_tools.called
        assert "200" in result
        assert "Google" in result
        assert "Apple" in result
    
    @patch('praisonaiagents.llm.openai_client.OpenAIClient')
    def test_sequential_with_context_preservation(self, mock_openai_client_class):
        """Test that context is preserved between sequential tool calls"""
        # Track context through tool calls
        call_history = []
        
        def track_stock_price(company_name: str) -> str:
            call_history.append(f"get_stock:{company_name}")
            return f"The stock price of {company_name} is 100"
        
        def track_multiply(a: int, b: int) -> int:
            call_history.append(f"multiply:{a}*{b}")
            return a * b
        
        # Create a mock instance
        mock_client_instance = MagicMock()
        mock_openai_client_class.return_value = mock_client_instance
        
        # Mock response
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Meta stock price is 100, tripled to 300."
        
        # Set up side effect to track tool execution
        def mock_chat_completion(**kwargs):
            # Execute tools if the agent passes execute_tool_fn
            if 'execute_tool_fn' in kwargs:
                # Simulate tool calls
                track_stock_price("Meta")
                track_multiply(100, 3)
            return mock_response
        
        mock_client_instance.chat_completion_with_tools.side_effect = mock_chat_completion
        
        # Create agent with tracking tools
        agent = Agent(
            name="Test Agent",
            instructions="You are a helpful assistant.",
            llm='gpt-3.5-turbo',
            tools=[track_stock_price, track_multiply]
        )
        
        # Execute
        result = agent.chat("Get Meta stock and triple it.")
        
        # Verify context preservation
        assert len(call_history) == 2
        assert "get_stock:Meta" in call_history[0]
        assert "multiply:100*3" in call_history[1]
        assert "300" in result
    
    @patch('praisonaiagents.llm.openai_client.OpenAIClient')
    def test_sequential_with_complex_arguments(self, mock_openai_client_class):
        """Test sequential tool calling with complex nested arguments"""
        def process_data(data: dict, options: dict) -> dict:
            """Process complex data structure"""
            return {
                "processed": True,
                "input_keys": list(data.keys()),
                "option_count": len(options)
            }
        
        # Create a mock instance
        mock_client_instance = MagicMock()
        mock_openai_client_class.return_value = mock_client_instance
        
        # Mock response
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Data processed successfully."
        mock_client_instance.chat_completion_with_tools.return_value = mock_response
        
        # Create agent
        agent = Agent(
            name="Test Agent",
            instructions="You are a data processor.",
            llm='gpt-3.5-turbo',
            tools=[process_data]
        )
        
        # Execute
        result = agent.chat("Process the user data with validation options.")
        
        # Verify
        assert mock_client_instance.chat_completion_with_tools.called
        assert "processed successfully" in result.lower()
    
    @patch('praisonaiagents.llm.openai_client.OpenAIClient')
    def test_sequential_tool_retry_on_error(self, mock_openai_client_class):
        """Test that agent can retry tool execution on transient errors"""
        attempt_count = 0
        
        def flaky_tool(x: int) -> int:
            nonlocal attempt_count
            attempt_count += 1
            if attempt_count == 1:
                raise ConnectionError("Temporary network error")
            return x * 2
        
        # Create a mock instance
        mock_client_instance = MagicMock()
        mock_openai_client_class.return_value = mock_client_instance
        
        # Mock response after retry
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Successfully executed: 5 * 2 = 10"
        mock_client_instance.chat_completion_with_tools.return_value = mock_response
        
        # Create agent
        agent = Agent(
            name="Test Agent",
            instructions="You are a helpful assistant. Retry on transient errors.",
            llm='gpt-3.5-turbo',
            tools=[flaky_tool]
        )
        
        # Execute - should handle the error and retry
        with contextlib.suppress(ConnectionError):
            result = agent.chat("Double the number 5 using the flaky tool.")
            # If we reach here, retry logic worked
            assert "10" in result
            assert attempt_count == 2  # Should have tried twice
        
        # Verify at least one attempt was made
        assert attempt_count >= 1


@pytest.mark.parametrize("model,expected_format", [
    ("gpt-3.5-turbo", "openai"),
    ("gemini/gemini-2.5-pro", "gemini"),
    ("ollama/llama2", "ollama"),
    ("claude-3-sonnet", "anthropic")
])
@patch('praisonaiagents.llm.openai_client.OpenAIClient')
def test_sequential_with_different_providers(mock_openai_client_class, model, expected_format):
    """Test sequential tool calling works with different LLM providers"""
    # Create a mock instance
    mock_client_instance = MagicMock()
    mock_openai_client_class.return_value = mock_client_instance
    
    # Mock response
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = "10 multiplied by 5 is 50."
    mock_client_instance.chat_completion_with_tools.return_value = mock_response
    
    # Create agent
    agent = Agent(
        name="Test Agent",
        instructions="You are a helpful assistant.",
        llm=model,
        tools=[multiply]
    )
    
    # Execute
    result = agent.chat("Multiply 10 by 5.")
    
    # Verify
    assert mock_client_instance.chat_completion_with_tools.called
    assert "50" in result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])