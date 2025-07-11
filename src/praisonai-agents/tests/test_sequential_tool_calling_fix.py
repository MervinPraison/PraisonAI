#!/usr/bin/env python3
"""
Unit test for sequential tool calling fix (Issue #824).
Tests that tool outputs are passed back to the LLM for further processing
instead of being returned directly to the user.
"""

import unittest
from unittest.mock import Mock, patch, MagicMock
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from praisonaiagents.llm.llm import LLM


class TestSequentialToolCalling(unittest.TestCase):
    """Test cases for sequential tool calling functionality"""
    
    def setUp(self):
        """Set up test fixtures"""
        self.llm = LLM(model="gemini/gemini-1.5-pro")
        
    @patch('praisonaiagents.llm.llm.litellm.completion')
    def test_sequential_tool_execution(self, mock_completion):
        """Test that tools can be called sequentially"""
        
        # Mock tool execution function
        tool_call_count = 0
        def mock_execute_tool(tool_name, args):
            nonlocal tool_call_count
            tool_call_count += 1
            if tool_name == "get_stock_price":
                return "100"
            elif tool_name == "multiply":
                return 200
            return None
        
        # Mock LLM responses
        # First response: call get_stock_price
        first_response = Mock()
        first_response.choices = [Mock()]
        first_response.choices[0].message = {
            "content": "I'll get the stock price first.",
            "tool_calls": [{
                "id": "call_1",
                "function": {
                    "name": "get_stock_price",
                    "arguments": '{"company_name": "Google"}'
                }
            }]
        }
        
        # Second response: call multiply based on first tool result
        second_response = Mock()
        second_response.choices = [Mock()]
        second_response.choices[0].message = {
            "content": "Now I'll multiply the price.",
            "tool_calls": [{
                "id": "call_2", 
                "function": {
                    "name": "multiply",
                    "arguments": '{"a": 100, "b": 2}'
                }
            }]
        }
        
        # Third response: final answer with no more tool calls
        third_response = Mock()
        third_response.choices = [Mock()]
        third_response.choices[0].message = {
            "content": "The stock price of Google is 100, and when multiplied by 2, it equals 200.",
            "tool_calls": None
        }
        
        # Set up mock to return different responses in sequence
        mock_completion.side_effect = [first_response, second_response, third_response]
        
        # Define tools
        tools = [
            {
                "name": "get_stock_price",
                "description": "Get stock price",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "company_name": {"type": "string"}
                    }
                }
            },
            {
                "name": "multiply",
                "description": "Multiply two numbers",
                "parameters": {
                    "type": "object", 
                    "properties": {
                        "a": {"type": "integer"},
                        "b": {"type": "integer"}
                    }
                }
            }
        ]
        
        # Execute the test
        result = self.llm.get_response(
            prompt="Get the stock price of Google and multiply it by 2",
            tools=tools,
            execute_tool_fn=mock_execute_tool,
            verbose=False
        )
        
        # Assertions
        self.assertEqual(tool_call_count, 2, "Both tools should have been called")
        self.assertIn("200", result, "Final result should include the multiplication result")
        self.assertEqual(mock_completion.call_count, 3, "LLM should be called 3 times (initial + 2 tool responses)")
        
    @patch('praisonaiagents.llm.llm.litellm.completion')
    def test_no_premature_return_after_tool_call(self, mock_completion):
        """Test that the response doesn't return immediately after first tool call"""
        
        tool_calls = []
        def mock_execute_tool(tool_name, args):
            tool_calls.append(tool_name)
            return f"Result from {tool_name}"
        
        # First response with tool call
        first_response = Mock()
        first_response.choices = [Mock()]
        first_response.choices[0].message = {
            "content": "Calling first tool",
            "tool_calls": [{
                "id": "call_1",
                "function": {
                    "name": "tool1",
                    "arguments": '{}'
                }
            }]
        }
        
        # Second response should be allowed (not cut off)
        second_response = Mock()
        second_response.choices = [Mock()] 
        second_response.choices[0].message = {
            "content": "Based on tool1 result, calling tool2",
            "tool_calls": [{
                "id": "call_2",
                "function": {
                    "name": "tool2", 
                    "arguments": '{}'
                }
            }]
        }
        
        # Final response
        final_response = Mock()
        final_response.choices = [Mock()]
        final_response.choices[0].message = {
            "content": "Processed both tools successfully",
            "tool_calls": None
        }
        
        mock_completion.side_effect = [first_response, second_response, final_response]
        
        result = self.llm.get_response(
            prompt="Use multiple tools",
            tools=[{"name": "tool1"}, {"name": "tool2"}],
            execute_tool_fn=mock_execute_tool,
            verbose=False
        )
        
        # Verify both tools were called
        self.assertEqual(len(tool_calls), 2, "Both tools should have been executed")
        self.assertIn("tool1", tool_calls)
        self.assertIn("tool2", tool_calls)
        

class TestGeminiModelSupport(unittest.TestCase):
    """Test cases for Gemini model configuration"""
    
    def test_gemini_models_support_structured_outputs(self):
        """Test that Gemini models are properly configured"""
        from praisonaiagents.llm.model_capabilities import supports_structured_outputs, supports_streaming_with_tools
        
        gemini_models = [
            "gemini-2.5-flash-lite-preview-06-17",
            "gemini-1.5-pro",
            "gemini-1.5-flash",
            "gemini/gemini-1.5-pro",
            "vertex_ai/gemini-pro"
        ]
        
        for model in gemini_models:
            with self.subTest(model=model):
                self.assertTrue(
                    supports_structured_outputs(model),
                    f"{model} should support structured outputs"
                )
                self.assertTrue(
                    supports_streaming_with_tools(model),
                    f"{model} should support streaming with tools"
                )


if __name__ == "__main__":
    unittest.main()