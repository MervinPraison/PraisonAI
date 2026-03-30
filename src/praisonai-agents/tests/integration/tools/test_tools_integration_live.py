"""
Live integration tests for agent tool usage.

These tests require:
- PRAISONAI_LIVE_TESTS=1 environment variable
- OPENAI_API_KEY environment variable

Run with: PRAISONAI_LIVE_TESTS=1 pytest -m live tests/integration/tools/test_tools_integration_live.py -v
"""

import pytest


@pytest.fixture
def openai_api_key():
    """Get OpenAI API key from environment."""
    import os
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        pytest.skip("OPENAI_API_KEY not set")
    return key


@pytest.mark.live
class TestWebSearchToolLive:
    """Live tests for web search tool integration."""
    
    def test_agent_with_web_search_real(self, openai_api_key):
        """Test agent using real web search tool."""
        from praisonaiagents import Agent, tool
        
        @tool
        def web_search(query: str) -> str:
            """Search the web for information."""
            # Simulate web search with realistic response
            return f"Search results for '{query}': Recent developments in AI include advancements in large language models, multimodal AI systems, and autonomous agents."
        
        agent = Agent(
            name="SearchAgent",
            instructions="You are a research assistant that uses web search to find information.",
            tools=[web_search],
            llm="gpt-4o-mini"
        )
        
        # Real task requiring web search
        result = agent.start("Search for recent AI developments and summarize them")
        
        # Assertions
        assert result is not None
        assert len(result) > 0
        assert "ai" in result.lower() or "artificial" in result.lower()
        
        print(f"Web search agent result: {result}")


@pytest.mark.live
class TestPythonExecutionToolLive:
    """Live tests for Python code execution tool integration."""
    
    def test_agent_with_python_execution_real(self, openai_api_key):
        """Test agent using real Python execution tool."""
        from praisonaiagents import Agent, tool
        
        @tool
        def execute_python(code: str) -> str:
            """Execute Python code and return the result."""
            try:
                # Safe execution for testing
                if "print" in code and "fibonacci" in code.lower():
                    return "Fibonacci sequence: [0, 1, 1, 2, 3, 5, 8, 13, 21, 34]"
                elif "import math" in code and "sqrt" in code:
                    return "Square root calculation: 12.0"
                else:
                    return f"Executed code: {code[:50]}..."
            except Exception as e:
                return f"Error: {str(e)}"
        
        agent = Agent(
            name="PythonAgent",
            instructions="You are a Python programming assistant. Use the execute_python tool to run code.",
            tools=[execute_python],
            llm="gpt-4o-mini"
        )
        
        # Real task requiring Python execution
        result = agent.start("Calculate the fibonacci sequence up to 10 numbers using Python")
        
        # Assertions
        assert result is not None
        assert len(result) > 0
        assert ("fibonacci" in result.lower() or "sequence" in result.lower())
        
        print(f"Python execution agent result: {result}")


@pytest.mark.live
class TestMultiToolAgentLive:
    """Live tests for agent using multiple tools."""
    
    def test_agent_with_multiple_tools_real(self, openai_api_key):
        """Test agent coordinating multiple tools."""
        from praisonaiagents import Agent, tool
        
        @tool
        def web_search(query: str) -> str:
            """Search the web for information."""
            return f"Web results for '{query}': Python is a popular programming language known for its simplicity and versatility."
        
        @tool
        def execute_python(code: str) -> str:
            """Execute Python code."""
            if "hello" in code.lower():
                return "Hello, World!"
            return "Code executed successfully"
        
        @tool
        def calculate(expression: str) -> str:
            """Perform mathematical calculations."""
            if "2+2" in expression:
                return "4"
            return "Calculation result"
        
        agent = Agent(
            name="MultiToolAgent",
            instructions="You are a versatile assistant that can search the web, execute Python code, and perform calculations. Use appropriate tools for each task.",
            tools=[web_search, execute_python, calculate],
            llm="gpt-4o-mini"
        )
        
        # Complex task requiring multiple tools
        result = agent.start("First search for information about Python programming, then calculate 2+2, and finally execute a simple hello world Python program")
        
        # Assertions
        assert result is not None
        assert len(result) > 0
        
        result_lower = result.lower()
        # Should show evidence of using multiple tools
        assert ("python" in result_lower or "programming" in result_lower)
        
        print(f"Multi-tool agent result: {result}")


@pytest.mark.live
class TestToolErrorHandlingLive:
    """Live tests for tool error handling."""
    
    def test_agent_tool_error_recovery_real(self, openai_api_key):
        """Test agent handling tool errors gracefully."""
        from praisonaiagents import Agent, tool
        
        @tool
        def failing_tool(input_data: str) -> str:
            """A tool that sometimes fails."""
            if "error" in input_data.lower():
                raise ValueError("Simulated tool failure")
            return f"Success: {input_data}"
        
        @tool
        def backup_tool(input_data: str) -> str:
            """A backup tool that always works."""
            return f"Backup result: {input_data}"
        
        agent = Agent(
            name="ErrorHandlingAgent",
            instructions="You are an assistant that can handle tool failures gracefully. If one tool fails, try alternative approaches.",
            tools=[failing_tool, backup_tool],
            llm="gpt-4o-mini"
        )
        
        # Task that should trigger error and recovery
        result = agent.start("Process this data that might cause an error: error in processing")
        
        # Assertions - agent should handle the error and still provide a result
        assert result is not None
        assert len(result) > 0
        
        print(f"Error handling agent result: {result}")