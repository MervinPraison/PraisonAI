"""
Unit tests for Agent type casting functionality.

Tests the _cast_arguments() method that converts string arguments 
to their expected types based on function signatures.

Issue: #410 - Agent calling tool calls always expects strings even if its integer
"""

import unittest
from unittest.mock import Mock, patch
import sys
import os

# Add the source directory to the path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../../src/praisonai-agents'))

from praisonaiagents.agent.agent import Agent


class TestAgentTypeCasting(unittest.TestCase):
    """Test cases for Agent type casting functionality."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.agent = Agent(
            name="TestAgent",
            role="Type Casting Tester",
            goal="Test type casting functionality"
        )
    
    def test_cast_arguments_integer_conversion(self):
        """Test casting string arguments to integers."""
        # Define a test function with integer parameter
        def test_function(count: int) -> str:
            return f"Count: {count}"
        
        # Mock arguments as they would come from JSON (all strings)
        arguments = {"count": "42"}
        
        # Test the casting (when _cast_arguments method exists)
        if hasattr(self.agent, '_cast_arguments'):
            casted_args = self.agent._cast_arguments(test_function, arguments)
            self.assertEqual(casted_args["count"], 42)
            self.assertIsInstance(casted_args["count"], int)
        else:
            self.skipTest("_cast_arguments method not implemented yet")
    
    def test_cast_arguments_float_conversion(self):
        """Test casting string arguments to floats."""
        def test_function(price: float) -> str:
            return f"Price: ${price}"
        
        arguments = {"price": "3.14"}
        
        if hasattr(self.agent, '_cast_arguments'):
            casted_args = self.agent._cast_arguments(test_function, arguments)
            self.assertEqual(casted_args["price"], 3.14)
            self.assertIsInstance(casted_args["price"], float)
        else:
            self.skipTest("_cast_arguments method not implemented yet")
    
    def test_cast_arguments_boolean_conversion(self):
        """Test casting string arguments to booleans."""
        def test_function(enabled: bool) -> str:
            return f"Enabled: {enabled}"
        
        # Test various boolean representations
        test_cases = [
            ({"enabled": "true"}, True),
            ({"enabled": "True"}, True),
            ({"enabled": "false"}, False),
            ({"enabled": "False"}, False),
        ]
        
        if hasattr(self.agent, '_cast_arguments'):
            for arguments, expected in test_cases:
                with self.subTest(arguments=arguments):
                    casted_args = self.agent._cast_arguments(test_function, arguments)
                    self.assertEqual(casted_args["enabled"], expected)
                    self.assertIsInstance(casted_args["enabled"], bool)
        else:
            self.skipTest("_cast_arguments method not implemented yet")
    
    def test_cast_arguments_mixed_types(self):
        """Test casting mixed argument types."""
        def test_function(count: int, price: float, enabled: bool, name: str) -> str:
            return f"Mixed: {count}, {price}, {enabled}, {name}"
        
        arguments = {
            "count": "10",
            "price": "99.99",
            "enabled": "true",
            "name": "test_item"
        }
        
        if hasattr(self.agent, '_cast_arguments'):
            casted_args = self.agent._cast_arguments(test_function, arguments)
            
            self.assertEqual(casted_args["count"], 10)
            self.assertIsInstance(casted_args["count"], int)
            
            self.assertEqual(casted_args["price"], 99.99)
            self.assertIsInstance(casted_args["price"], float)
            
            self.assertEqual(casted_args["enabled"], True)
            self.assertIsInstance(casted_args["enabled"], bool)
            
            # String should remain unchanged
            self.assertEqual(casted_args["name"], "test_item")
            self.assertIsInstance(casted_args["name"], str)
        else:
            self.skipTest("_cast_arguments method not implemented yet")
    
    def test_cast_arguments_no_annotations(self):
        """Test that functions without type annotations remain unchanged."""
        def test_function(value):
            return f"Value: {value}"
        
        arguments = {"value": "42"}
        
        if hasattr(self.agent, '_cast_arguments'):
            casted_args = self.agent._cast_arguments(test_function, arguments)
            # Without annotations, should remain as string
            self.assertEqual(casted_args["value"], "42")
            self.assertIsInstance(casted_args["value"], str)
        else:
            self.skipTest("_cast_arguments method not implemented yet")
    
    def test_cast_arguments_conversion_failure_graceful(self):
        """Test graceful fallback when type conversion fails."""
        def test_function(count: int) -> str:
            return f"Count: {count}"
        
        # Invalid integer string should fallback gracefully
        arguments = {"count": "not_a_number"}
        
        if hasattr(self.agent, '_cast_arguments'):
            casted_args = self.agent._cast_arguments(test_function, arguments)
            # Should fallback to original string value
            self.assertEqual(casted_args["count"], "not_a_number")
            self.assertIsInstance(casted_args["count"], str)
        else:
            self.skipTest("_cast_arguments method not implemented yet")
    
    def test_cast_arguments_already_correct_type(self):
        """Test that arguments already of correct type are not modified."""
        def test_function(count: int) -> str:
            return f"Count: {count}"
        
        # Already an integer
        arguments = {"count": 42}
        
        if hasattr(self.agent, '_cast_arguments'):
            casted_args = self.agent._cast_arguments(test_function, arguments)
            self.assertEqual(casted_args["count"], 42)
            self.assertIsInstance(casted_args["count"], int)
        else:
            self.skipTest("_cast_arguments method not implemented yet")
    
    def test_cast_arguments_with_none_values(self):
        """Test handling of None values."""
        def test_function(optional_count: int = None) -> str:
            return f"Count: {optional_count}"
        
        arguments = {"optional_count": None}
        
        if hasattr(self.agent, '_cast_arguments'):
            casted_args = self.agent._cast_arguments(test_function, arguments)
            self.assertIsNone(casted_args["optional_count"])
        else:
            self.skipTest("_cast_arguments method not implemented yet")


if __name__ == '__main__':
    unittest.main()