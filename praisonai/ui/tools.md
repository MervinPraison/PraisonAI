# Understanding Tool Integration in AI Agents - A Beginner's Guide

## Overview
This guide explains how to properly integrate tools (functions) that an AI agent can use, making them both understandable to the OpenAI API and executable by your code.

## Key Components

### 1. Tool Definition Structure
```python
# Example tool definition in tools.py
def search_tool(query: str) -> list:
    """
    Perform a web search using DuckDuckGo.

    Args:
        query (str): The search query string.

    Returns:
        list: Search results with title, url, and snippet.
    """
    # Function implementation...
```

### 2. Tool Dictionary Format
```python
tools_dict = {
    'search_tool': {
        'type': 'function',
        'function': {
            'name': 'search_tool',
            'description': '...', 
            'parameters': {
                'type': 'object',
                'properties': {
                    'query': {'type': 'string'}
                }
            }
        },
        'callable': search_tool  # The actual Python function
    }
}
```

## The Two-Part System

### Part 1: OpenAI API Communication
```python
# task_tools: What OpenAI understands
task_tools = []
tool_def = tools_dict[tool_name].copy()
callable_func = tool_def.pop("callable")  # Remove the Python function
task_tools.append(tool_def)  # Add clean JSON-serializable definition
```

### Part 2: Function Execution
```python
# role_tools: What your code executes
role_tools = []
role_tools.append(callable_func)  # Store the actual function
agent.tools = role_tools  # Give agent access to executable functions
```

## Putting It All Together

```python
# Initialize empty lists
role_tools = []  # For executable functions
task_tools = []  # For OpenAI API definitions

# Process each tool
for tool_name in tools_list:
    if tool_name in tools_dict:
        # 1. Get the tool definition
        tool_def = tools_dict[tool_name].copy()
        
        # 2. Separate the callable function
        callable_func = tool_def.pop("callable")
        
        # 3. Store the function for execution
        role_tools.append(callable_func)
        
        # 4. Store the API definition
        task_tools.append(tool_def)
        
        # 5. Give agent access to functions
        agent.tools = role_tools

# Create task with API definitions
task = Task(
    description="...",
    tools=task_tools,  # OpenAI API will use these
    agent=agent,       # Agent has access to callable functions
    # ... other parameters ...
)
```

## Why This Works

1. **API Communication**
   - OpenAI API receives clean JSON tool definitions
   - No Python functions that would cause serialization errors

2. **Function Execution**
   - Agent has access to actual Python functions
   - Can execute tools when OpenAI decides to use them

3. **Separation of Concerns**
   - `task_tools`: Describes what tools can do (for OpenAI)
   - `role_tools`: Actually does the work (for Python)

## Common Errors and Solutions

1. **"Invalid type for 'tools[0]'"**
   - Cause: Sending null or invalid tool definition to OpenAI
   - Solution: Use proper tool definition format in `task_tools`

2. **"Object of type function is not JSON serializable"**
   - Cause: Trying to send Python function to OpenAI API
   - Solution: Remove callable function from API definition

3. **"Tool is not callable"**
   - Cause: Agent doesn't have access to executable functions
   - Solution: Set `agent.tools = role_tools`

## Best Practices

1. Always initialize both `task_tools` and `role_tools` lists
2. Make clean copies of tool definitions to avoid modifying originals
3. Keep tool definitions JSON-serializable for API communication
4. Ensure agents have access to callable functions
5. Document tool parameters and return values clearly

This structure maintains clean separation between API communication and actual function execution, making your AI agent system both reliable and maintainable.
