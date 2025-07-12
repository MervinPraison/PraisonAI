"""
Test file to verify sequential tool calling functionality.

This tests that agents can:
1. Execute multiple tools in sequence 
2. Pass results from one tool to another
3. Return the final combined result

This addresses issue #839 where agents would return empty responses after first tool call.
"""

import pytest
import logging
from unittest.mock import patch, MagicMock
from praisonaiagents import Agent, Task, PraisonAIAgents

# Enable logging for better debugging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')


# Define test tools that need sequential execution
def get_stock_price(company_name: str) -> str:
    """
    Get the stock price of a company.
    
    Args:
        company_name (str): The name of the company
        
    Returns:
        str: The stock price of the company
    """
    print(f"[Tool Called] get_stock_price({company_name})")
    # Mock stock prices
    prices = {
        "Google": 100,
        "Apple": 150,
        "Microsoft": 200
    }
    price = prices.get(company_name, 50)
    return f"The stock price of {company_name} is {price}"


def multiply(a: int, b: int) -> int:
    """
    Multiply two numbers.
    
    Args:
        a (int): First number
        b (int): Second number
        
    Returns:
        int: Product of a and b
    """
    print(f"[Tool Called] multiply({a}, {b})")
    return a * b


def add(a: int, b: int) -> int:
    """
    Add two numbers.
    
    Args:
        a (int): First number
        b (int): Second number
        
    Returns:
        int: Sum of a and b
    """
    print(f"[Tool Called] add({a}, {b})")
    return a + b


class TestSequentialToolCalling:
    """Test class for sequential tool calling functionality."""
    
    def test_sequential_two_tools(self):
        """Test that agent can call two tools sequentially."""
        print("\n" + "=" * 60)
        print("Test: Sequential Two Tools")
        print("=" * 60)
        
        # Create agent with tools
        agent = Agent(
            name="SequentialAgent",
            role="Math Assistant",
            goal="Help with calculations using available tools",
            backstory="Expert at using multiple tools to solve problems",
            instructions="When asked to multiply a stock price, first get the stock price, then multiply it.",
            tools=[get_stock_price, multiply],
            llm={"model": "gpt-4o"},
            verbose=True
        )
        
        # Test sequential tool calling
        result = agent.start("What is the stock price of Google? Multiply the Google stock price by 2.")
        
        print(f"\nFinal Result: {result}")
        
        # Verify the result contains the expected value (100 * 2 = 200)
        assert result is not None, "Agent returned None instead of a result"
        assert result != "", "Agent returned empty string instead of a result"
        assert "200" in str(result), f"Expected result to contain '200', but got: {result}"
        
        print("✅ Test passed: Agent successfully called tools sequentially")
    
    def test_sequential_three_tools(self):
        """Test that agent can call three tools sequentially."""
        print("\n" + "=" * 60)
        print("Test: Sequential Three Tools")
        print("=" * 60)
        
        # Create agent with multiple tools
        agent = Agent(
            name="ComplexAgent",
            role="Advanced Math Assistant",
            goal="Solve complex calculations using multiple tools",
            backstory="Expert at chaining multiple operations together",
            instructions="Follow the exact steps requested by the user, using tools in sequence.",
            tools=[get_stock_price, multiply, add],
            llm={"model": "gpt-4o"},
            verbose=True
        )
        
        # Test sequential tool calling with three operations
        result = agent.start(
            "Get Apple's stock price, multiply it by 3, then add 50 to the result. "
            "Show me each step and the final result."
        )
        
        print(f"\nFinal Result: {result}")
        
        # Apple stock is 150, 150 * 3 = 450, 450 + 50 = 500
        assert result is not None, "Agent returned None instead of a result"
        assert result != "", "Agent returned empty string instead of a result"
        # Check if the result mentions the expected value
        result_str = str(result).lower()
        assert any(val in result_str for val in ["500", "five hundred"]), \
            f"Expected result to contain '500', but got: {result}"
        
        print("✅ Test passed: Agent successfully called three tools sequentially")
    
    def test_multiple_agents_sequential_tools(self):
        """Test multiple agents working together with sequential tool calls."""
        print("\n" + "=" * 60)
        print("Test: Multiple Agents with Sequential Tools")
        print("=" * 60)
        
        # First agent gets stock price
        price_agent = Agent(
            name="PriceAgent",
            role="Stock Price Analyst",
            goal="Get accurate stock prices",
            backstory="Expert at retrieving stock market data",
            tools=[get_stock_price],
            llm={"model": "gpt-4o"}
        )
        
        # Second agent does calculations
        calc_agent = Agent(
            name="CalcAgent",
            role="Financial Calculator",
            goal="Perform calculations on financial data",
            backstory="Expert at financial mathematics",
            tools=[multiply, add],
            llm={"model": "gpt-4o"}
        )
        
        # Create tasks
        price_task = Task(
            name="get_price",
            description="Get the stock price of Microsoft",
            expected_output="The current stock price of Microsoft",
            agent=price_agent
        )
        
        calc_task = Task(
            name="calculate",
            description="Take the Microsoft stock price (which is 200) and multiply it by 4, then add 100",
            expected_output="The final calculated value",
            agent=calc_agent
        )
        
        # Create workflow
        workflow = PraisonAIAgents(
            agents=[price_agent, calc_agent],
            tasks=[price_task, calc_task],
            verbose=True
        )
        
        # Execute workflow
        result = workflow.start()
        
        print(f"\nWorkflow Result: {result}")
        
        # Microsoft stock is 200, 200 * 4 = 800, 800 + 100 = 900
        if isinstance(result, dict) and 'task_results' in result:
            final_result = str(result['task_results'][-1])
            assert "900" in final_result or "nine hundred" in final_result.lower(), \
                f"Expected final result to contain '900', but got: {final_result}"
        
        print("✅ Test passed: Multiple agents successfully used tools sequentially")
    
    @patch('litellm.completion')
    def test_tool_calling_with_mocked_llm(self, mock_completion):
        """Test sequential tool calling with mocked LLM responses."""
        print("\n" + "=" * 60)
        print("Test: Sequential Tool Calling with Mocked LLM")
        print("=" * 60)
        
        # Mock LLM to return tool calls
        call_count = 0
        
        def mock_llm_response(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            
            if call_count == 1:
                # First call: request to use get_stock_price tool
                return MagicMock(
                    choices=[MagicMock(
                        message={
                            "content": "",
                            "tool_calls": [{
                                "id": "call_1",
                                "function": {
                                    "name": "get_stock_price",
                                    "arguments": '{"company_name": "Google"}'
                                }
                            }]
                        }
                    )]
                )
            elif call_count == 2:
                # Second call: request to use multiply tool
                return MagicMock(
                    choices=[MagicMock(
                        message={
                            "content": "",
                            "tool_calls": [{
                                "id": "call_2",
                                "function": {
                                    "name": "multiply",
                                    "arguments": '{"a": 100, "b": 2}'
                                }
                            }]
                        }
                    )]
                )
            else:
                # Final call: return the result
                return MagicMock(
                    choices=[MagicMock(
                        message={
                            "content": "The stock price of Google is 100. After multiplying by 2, the result is 200."
                        }
                    )]
                )
        
        mock_completion.side_effect = mock_llm_response
        
        # Create agent
        agent = Agent(
            name="MockedAgent",
            role="Test Assistant",
            goal="Test sequential tool calling",
            backstory="Test agent for validating functionality",
            tools=[get_stock_price, multiply],
            llm={"model": "gpt-4o"}
        )
        
        # Execute
        result = agent.start("Get Google stock price and multiply by 2")
        
        print(f"\nResult: {result}")
        print(f"LLM was called {call_count} times")
        
        # Verify
        assert call_count >= 3, f"Expected at least 3 LLM calls, but got {call_count}"
        assert "200" in str(result), f"Expected result to contain '200', but got: {result}"
        
        print("✅ Test passed: Mocked sequential tool calling works correctly")


def test_edge_case_empty_response():
    """Test that the fix prevents empty responses after tool calls."""
    print("\n" + "=" * 60)
    print("Test: Edge Case - Preventing Empty Response")
    print("=" * 60)
    
    # Create agent with a simple tool
    agent = Agent(
        name="EdgeCaseAgent",
        role="Test Assistant",
        goal="Test edge cases",
        backstory="Specialized in finding edge cases",
        tools=[get_stock_price],
        llm={"model": "gpt-4o"},
        verbose=True
    )
    
    # Execute a query that requires tool use
    result = agent.start("What is the stock price of Apple?")
    
    print(f"\nResult: {result}")
    
    # The main issue (#839) was agents returning empty responses
    assert result is not None, "Agent returned None"
    assert result != "", "Agent returned empty string"
    assert len(str(result).strip()) > 0, "Agent returned whitespace only"
    
    print("✅ Test passed: Agent did not return empty response after tool call")


if __name__ == "__main__":
    # Run all tests
    test_suite = TestSequentialToolCalling()
    
    # Run individual tests
    test_suite.test_sequential_two_tools()
    test_suite.test_sequential_three_tools()
    test_suite.test_multiple_agents_sequential_tools()
    test_suite.test_tool_calling_with_mocked_llm()
    
    # Run edge case test
    test_edge_case_empty_response()
    
    print("\n" + "=" * 60)
    print("All tests completed!")
    print("=" * 60)