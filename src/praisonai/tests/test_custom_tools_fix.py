#!/usr/bin/env python3
"""
Test script to verify the custom tools fix in chatbot integration.
This demonstrates that agents can now use multiple custom tools when integrated into the chatbot.
"""

import yaml
import os

# Create a sample agents.yaml file
agents_yaml_content = """
roles:
  researcher:
    name: "Research Agent"
    role: "Information Researcher"
    goal: "Find and analyze information using multiple tools"
    backstory: "You are an expert researcher with access to multiple information sources"
    llm: "gpt-4o-mini"
    tools:
      - search_web
      - get_weather
      - calculate
    tasks:
      test_task:
        description: "Use all available tools to gather information about {topic}"
        expected_output: "A comprehensive report using data from all tools"
"""

# Create a sample tools.py file
tools_py_content = '''
def search_web(query: str) -> str:
    """Search the web for information.
    
    Args:
        query: The search query
        
    Returns:
        Search results
    """
    return f"Web search results for: {query}"

def get_weather(location: str) -> str:
    """Get weather information for a location.
    
    Args:
        location: The location to get weather for
        
    Returns:
        Weather information
    """
    return f"Weather in {location}: Sunny, 25°C"

def calculate(expression: str) -> str:
    """Perform a calculation.
    
    Args:
        expression: Mathematical expression to evaluate
        
    Returns:
        Calculation result
    """
    try:
        result = eval(expression)
        return f"Result: {result}"
    except:
        return "Invalid expression"
'''

# Write the test files
with open("test_agents.yaml", "w") as f:
    f.write(agents_yaml_content)

with open("test_tools.py", "w") as f:
    f.write(tools_py_content)

print("Test files created successfully!")
print("\nTo test the fix:")
print("1. Copy test_agents.yaml to agents.yaml")
print("2. Copy test_tools.py to tools.py")
print("3. Run the chatbot UI")
print("4. Ask the agent to use multiple tools")
print("\nThe agent should now be able to use all three tools (search_web, get_weather, calculate)")
print("instead of just the last one.")
