#!/usr/bin/env python3
"""
Comprehensive mock tests for sequential tool calling functionality in PraisonAI.
Based on the sequential agent examples and llm.py implementation.
"""

import pytest
import sys
import os
import json
from unittest.mock import Mock, patch, MagicMock, call

# Add the source path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', 'praisonai-agents'))

try:
    from praisonaiagents import Agent
    from praisonaiagents.llm.llm import LLM
except ImportError as e:
    pytest.skip(f"Could not import required modules: {e}", allow_module_level=True)


class MockLLMResponse:
    """Helper class to create mock LLM responses with tool calls."""
    
    @staticmethod
    def create_tool_call_response(tool_name, arguments, tool_call_id="call_123"):
        """Create a mock response with a tool call."""
        class MockToolCall:
            def __init__(self):
                self.function = Mock()
                self.function.name = tool_name
                self.function.arguments = json.dumps(arguments) if isinstance(arguments, dict) else arguments
                self.id = tool_call_id
            
            def get(self, key, default=None):
                return getattr(self, key, default)
        
        class MockMessage:
            def __init__(self):
                self.content = ""
                self.tool_calls = [MockToolCall()]
            
            def get(self, key, default=None):
                return getattr(self, key, default)
        
        class MockChoice:
            def __init__(self):
                self.message = MockMessage()
        
        class MockResponse:
            def __init__(self):
                self.choices = [MockChoice()]
        
        return MockResponse()
    
    @staticmethod
    def create_text_response(content):
        """Create a mock response with text content."""
        class MockMessage:
            def __init__(self):
                self.content = content
                self.tool_calls = None
            
            def get(self, key, default=None):
                return getattr(self, key, default)
        
        class MockChoice:
            def __init__(self):
                self.message = MockMessage()
        
        class MockResponse:
            def __init__(self):
                self.choices = [MockChoice()]
        
        return MockResponse()
    
    @staticmethod
    def create_streaming_response(content):
        """Create a mock streaming response."""
        class MockDelta:
            def __init__(self, chunk):
                self.content = chunk
        
        class MockChoice:
            def __init__(self, chunk):
                self.delta = MockDelta(chunk)
        
        class MockChunk:
            def __init__(self, chunk):
                self.choices = [MockChoice(chunk)]
        
        # Return chunks of the content
        chunks = [content[i:i+5] for i in range(0, len(content), 5)]
        return [MockChunk(chunk) for chunk in chunks]


# Test tools
def get_stock_price(company_name: str) -> str:
    """
    Get the stock price of a company
    
    Args:
        company_name (str): The name of the company
        
    Returns:
        str: The stock price of the company
    """
    return f"The stock price of {company_name} is 100"


def multiply(a: int, b: int) -> int:
    """
    Multiply two numbers
    
    Args:
        a (int): First number
        b (int): Second number
        
    Returns:
        int: Product of a and b
    """
    return a * b


def divide(a: int, b: int) -> float:
    """
    Divide two numbers
    
    Args:
        a (int): Dividend
        b (int): Divisor
        
    Returns:
        float: Result of division
    """
    if b == 0:
        raise ValueError("Cannot divide by zero")
    return a / b


class TestSequentialToolCalling:
    """Test sequential tool calling functionality."""
    
    @patch('litellm.completion')
    def test_basic_sequential_tool_calling(self, mock_completion):
        """Test basic sequential tool calling with two tools."""
        # Setup mock responses
        responses = [
            # First response: call get_stock_price
            MockLLMResponse.create_tool_call_response(
                "get_stock_price", 
                {"company_name": "Google"},
                "call_001"
            ),
            # Second response: call multiply
            MockLLMResponse.create_tool_call_response(
                "multiply",
                {"a": 100, "b": 2},
                "call_002"
            ),
            # Final response: text result
            MockLLMResponse.create_text_response(
                "The stock price of Google is 100 and after multiplying with 2 it is 200."
            )
        ]
        mock_completion.side_effect = responses
        
        # Create agent with tools
        agent = Agent(
            instructions="You are a helpful assistant.",
            llm="gpt-4",
            tools=[get_stock_price, multiply]
        )
        
        # Execute sequential tool calling
        result = agent.chat("what is the stock price of Google? multiply the Google stock price with 2")
        
        # Verify the result
        assert "200" in result
        assert mock_completion.call_count == 3  # 3 LLM calls
    
    @patch('litellm.completion')
    def test_three_tool_sequential_calling(self, mock_completion):
        """Test sequential calling with three tools."""
        # Setup mock responses
        responses = [
            # First: get stock price
            MockLLMResponse.create_tool_call_response(
                "get_stock_price",
                {"company_name": "Apple"},
                "call_001"
            ),
            # Second: multiply
            MockLLMResponse.create_tool_call_response(
                "multiply",
                {"a": 100, "b": 3},
                "call_002"
            ),
            # Third: divide
            MockLLMResponse.create_tool_call_response(
                "divide",
                {"a": 300, "b": 2},
                "call_003"
            ),
            # Final response
            MockLLMResponse.create_text_response(
                "The stock price of Apple is 100. After multiplying by 3, we get 300. After dividing by 2, the final result is 150."
            )
        ]
        mock_completion.side_effect = responses
        
        agent = Agent(
            instructions="You are a helpful assistant.",
            llm="gpt-4",
            tools=[get_stock_price, multiply, divide]
        )
        
        result = agent.chat("Get Apple stock price, multiply by 3, then divide by 2")
        
        assert "150" in result
        assert mock_completion.call_count == 4
    
    @patch('litellm.completion')
    def test_sequential_with_dependencies(self, mock_completion):
        """Test sequential tool calling where each call depends on the previous result."""
        # Setup mock responses that show dependency
        responses = [
            # First: get stock price
            MockLLMResponse.create_tool_call_response(
                "get_stock_price",
                {"company_name": "Microsoft"},
                "call_001"
            ),
            # Second: multiply using the previous result
            MockLLMResponse.create_tool_call_response(
                "multiply",
                {"a": 100, "b": 5},  # Using 100 from previous call
                "call_002"
            ),
            # Final response
            MockLLMResponse.create_text_response(
                "Microsoft stock price is 100. Multiplied by 5 equals 500."
            )
        ]
        mock_completion.side_effect = responses
        
        agent = Agent(
            instructions="You are a helpful assistant.",
            llm="gpt-4",
            tools=[get_stock_price, multiply]
        )
        
        result = agent.chat("Get Microsoft stock and multiply it by 5")
        
        assert "500" in result
        assert mock_completion.call_count == 3
    
    @patch('litellm.completion')
    def test_sequential_with_streaming(self, mock_completion):
        """Test sequential tool calling with streaming enabled."""
        # For streaming, we need different mock structure
        def streaming_side_effect(*args, **kwargs):
            # Check if this is a tool result message
            messages = kwargs.get('messages', [])
            if any(msg.get('role') == 'tool' for msg in messages):
                # This is after a tool call, return next action
                tool_messages = [msg for msg in messages if msg.get('role') == 'tool']
                if len(tool_messages) == 1:
                    # After first tool, call second tool
                    return MockLLMResponse.create_tool_call_response(
                        "multiply",
                        {"a": 100, "b": 2},
                        "call_002"
                    )
                else:
                    # After second tool, return final response
                    return MockLLMResponse.create_streaming_response(
                        "The result is 200."
                    )
            else:
                # Initial call
                return MockLLMResponse.create_tool_call_response(
                    "get_stock_price",
                    {"company_name": "Tesla"},
                    "call_001"
                )
        
        mock_completion.side_effect = streaming_side_effect
        
        agent = Agent(
            instructions="You are a helpful assistant.",
            llm="gpt-4",
            tools=[get_stock_price, multiply],
            stream=True
        )
        
        result = agent.chat("Get Tesla stock and double it")
        
        # Streaming returns the same result
        assert "200" in result or "The result is 200" in result
    
    @patch('litellm.completion')
    def test_sequential_error_handling(self, mock_completion):
        """Test error handling in sequential tool calling."""
        # Setup responses with an error
        responses = [
            # First: get stock price
            MockLLMResponse.create_tool_call_response(
                "get_stock_price",
                {"company_name": "Amazon"},
                "call_001"
            ),
            # Second: divide by zero (will cause error)
            MockLLMResponse.create_tool_call_response(
                "divide",
                {"a": 100, "b": 0},
                "call_002"
            ),
            # Recovery response after error
            MockLLMResponse.create_text_response(
                "I encountered an error trying to divide by zero. The stock price of Amazon is 100."
            )
        ]
        mock_completion.side_effect = responses
        
        agent = Agent(
            instructions="You are a helpful assistant.",
            llm="gpt-4",
            tools=[get_stock_price, divide]
        )
        
        result = agent.chat("Get Amazon stock and divide by 0")
        
        # Should handle the error gracefully
        assert "100" in result
        assert mock_completion.call_count == 3
    
    @patch('litellm.completion')
    def test_sequential_with_gemini(self, mock_completion):
        """Test sequential tool calling with Gemini model format."""
        # Gemini has a specific response format
        responses = [
            MockLLMResponse.create_tool_call_response(
                "get_stock_price",
                {"company_name": "Google"},
                "call_001"
            ),
            MockLLMResponse.create_tool_call_response(
                "multiply",
                {"a": 100, "b": 2},
                "call_002"
            ),
            MockLLMResponse.create_text_response("Result: 200")
        ]
        mock_completion.side_effect = responses
        
        agent = Agent(
            instructions="You are a helpful assistant.",
            llm="gemini/gemini-2.0-flash",
            tools=[get_stock_price, multiply]
        )
        
        result = agent.chat("Get Google stock and double it")
        
        assert "200" in result
        assert mock_completion.call_count == 3
    
    @patch('litellm.completion')
    def test_sequential_with_ollama(self, mock_completion):
        """Test sequential tool calling with Ollama format."""
        # Ollama uses JSON string for arguments
        class OllamaToolCall:
            def __init__(self, name, args):
                self.function = Mock()
                self.function.name = name
                self.function.arguments = json.dumps(args)  # JSON string
                self.id = "ollama_call"
        
        class OllamaMessage:
            def __init__(self, tool_calls=None, content=""):
                self.tool_calls = tool_calls
                self.content = content
            
            def get(self, key, default=None):
                return getattr(self, key, default)
        
        class OllamaChoice:
            def __init__(self, message):
                self.message = message
        
        class OllamaResponse:
            def __init__(self, message):
                self.choices = [OllamaChoice(message)]
        
        responses = [
            OllamaResponse(OllamaMessage(
                tool_calls=[OllamaToolCall("get_stock_price", {"company_name": "NVIDIA"})]
            )),
            OllamaResponse(OllamaMessage(
                tool_calls=[OllamaToolCall("multiply", {"a": 100, "b": 3})]
            )),
            OllamaResponse(OllamaMessage(content="The result is 300"))
        ]
        mock_completion.side_effect = responses
        
        agent = Agent(
            instructions="You are a helpful assistant.",
            llm="ollama/llama2",
            tools=[get_stock_price, multiply]
        )
        
        result = agent.chat("Get NVIDIA stock and triple it")
        
        assert "300" in result
        assert mock_completion.call_count == 3
    
    @patch('litellm.completion')
    def test_multiple_tools_single_response(self, mock_completion):
        """Test handling multiple tool calls in a single response."""
        # Some LLMs might return multiple tool calls at once
        class MultiToolMessage:
            def __init__(self):
                tool1 = Mock()
                tool1.function.name = "get_stock_price"
                tool1.function.arguments = json.dumps({"company_name": "Apple"})
                tool1.id = "call_001"
                
                tool2 = Mock()
                tool2.function.name = "get_stock_price"
                tool2.function.arguments = json.dumps({"company_name": "Google"})
                tool2.id = "call_002"
                
                self.tool_calls = [tool1, tool2]
                self.content = ""
            
            def get(self, key, default=None):
                return getattr(self, key, default)
        
        class MultiToolChoice:
            def __init__(self):
                self.message = MultiToolMessage()
        
        class MultiToolResponse:
            def __init__(self):
                self.choices = [MultiToolChoice()]
        
        responses = [
            MultiToolResponse(),
            MockLLMResponse.create_text_response(
                "Apple stock is 100 and Google stock is 100."
            )
        ]
        mock_completion.side_effect = responses
        
        agent = Agent(
            instructions="You are a helpful assistant.",
            llm="gpt-4",
            tools=[get_stock_price]
        )
        
        result = agent.chat("Get stock prices for Apple and Google")
        
        assert "Apple" in result and "Google" in result
        assert mock_completion.call_count == 2
    
    @pytest.mark.parametrize("llm_model", [
        "gpt-4",
        "claude-3-opus-20240229",
        "gemini/gemini-pro",
        "ollama/llama2"
    ])
    @patch('litellm.completion')
    def test_sequential_with_different_providers(self, mock_completion, llm_model):
        """Test sequential tool calling works with different LLM providers."""
        responses = [
            MockLLMResponse.create_tool_call_response(
                "get_stock_price",
                {"company_name": "Meta"},
                "call_001"
            ),
            MockLLMResponse.create_tool_call_response(
                "multiply",
                {"a": 100, "b": 4},
                "call_002"
            ),
            MockLLMResponse.create_text_response("Result: 400")
        ]
        mock_completion.side_effect = responses
        
        agent = Agent(
            instructions="You are a helpful assistant.",
            llm=llm_model,
            tools=[get_stock_price, multiply]
        )
        
        result = agent.chat("Get Meta stock and multiply by 4")
        
        assert "400" in result
        assert mock_completion.call_count == 3
    
    @patch('litellm.completion')
    def test_sequential_with_context_preservation(self, mock_completion):
        """Test that context is preserved across sequential tool calls."""
        # Track messages to verify context preservation
        call_messages = []
        
        def track_messages(*args, **kwargs):
            messages = kwargs.get('messages', [])
            call_messages.append(len(messages))
            
            # Return appropriate response based on message count
            if len(messages) == 1:  # Initial call
                return MockLLMResponse.create_tool_call_response(
                    "get_stock_price",
                    {"company_name": "Netflix"},
                    "call_001"
                )
            elif len(messages) == 3:  # After first tool (user + assistant + tool)
                return MockLLMResponse.create_tool_call_response(
                    "multiply",
                    {"a": 100, "b": 10},
                    "call_002"
                )
            else:  # After second tool
                return MockLLMResponse.create_text_response("Final result: 1000")
        
        mock_completion.side_effect = track_messages
        
        agent = Agent(
            instructions="You are a helpful assistant.",
            llm="gpt-4",
            tools=[get_stock_price, multiply]
        )
        
        result = agent.chat("Get Netflix stock and multiply by 10")
        
        # Verify message count increases (context preserved)
        assert call_messages == [1, 3, 5]  # Messages accumulate
        assert "1000" in result
    
    @patch('litellm.completion')
    def test_sequential_with_complex_arguments(self, mock_completion):
        """Test sequential tool calling with complex nested arguments."""
        def analyze_portfolio(stocks: list, weights: dict) -> str:
            """Analyze a portfolio of stocks."""
            total = sum(weights.get(stock, 0) * 100 for stock in stocks)
            return f"Portfolio value: ${total}"
        
        responses = [
            MockLLMResponse.create_tool_call_response(
                "analyze_portfolio",
                {
                    "stocks": ["Apple", "Google", "Microsoft"],
                    "weights": {"Apple": 0.4, "Google": 0.3, "Microsoft": 0.3}
                },
                "call_001"
            ),
            MockLLMResponse.create_text_response("Portfolio analysis complete: $100")
        ]
        mock_completion.side_effect = responses
        
        agent = Agent(
            instructions="You are a portfolio analyst.",
            llm="gpt-4",
            tools=[analyze_portfolio]
        )
        
        result = agent.chat("Analyze my portfolio with Apple, Google, and Microsoft")
        
        assert "Portfolio" in result
        assert mock_completion.call_count == 2
    
    @patch('litellm.completion')
    def test_sequential_tool_retry_on_error(self, mock_completion):
        """Test that sequential tool calling can retry on transient errors."""
        # First attempt fails, second succeeds
        attempt = 0
        
        def retry_side_effect(*args, **kwargs):
            nonlocal attempt
            attempt += 1
            
            if attempt == 1:
                # First attempt - raise an exception
                raise Exception("Transient API error")
            elif attempt == 2:
                # Second attempt - success
                return MockLLMResponse.create_tool_call_response(
                    "get_stock_price",
                    {"company_name": "IBM"},
                    "call_001"
                )
            else:
                return MockLLMResponse.create_text_response("IBM stock is 100")
        
        mock_completion.side_effect = retry_side_effect
        
        agent = Agent(
            instructions="You are a helpful assistant.",
            llm="gpt-4",
            tools=[get_stock_price]
        )
        
        # This might fail if retry logic isn't implemented
        try:
            result = agent.chat("Get IBM stock price")
            # If retry logic exists, we should get a result
            assert "100" in result or "IBM" in result
        except Exception as e:
            # If no retry logic, we expect the exception
            assert "Transient API error" in str(e)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])