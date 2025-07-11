# Tool Call Fix Documentation

## Issue
Agents using Gemini models (`gemini/gemini-1.5-flash-8b`) were not calling provided tools, instead responding with "I do not have access to the internet" when tasked with searching.

## Root Cause
The Gemini model through LiteLLM was not being properly instructed to use the available tools. The system prompt didn't mention the tools, and the tool_choice parameter wasn't being set.

## Fix Applied (Updated)

### 1. Enhanced System Prompt (agent.py) - IMPROVED
When tools are available, the agent's system prompt now explicitly mentions them with better error handling:

```python
# In _build_messages method with enhanced error handling and MCP tool support
if self.tools:
    tool_names = []
    for tool in self.tools:
        try:
            if callable(tool) and hasattr(tool, '__name__'):
                tool_names.append(tool.__name__)
            elif isinstance(tool, dict) and isinstance(tool.get('function'), dict) and 'name' in tool['function']:
                tool_names.append(tool['function']['name'])
            elif isinstance(tool, str):
                tool_names.append(tool)
            elif hasattr(tool, "to_openai_tool"):
                # Handle MCP tools
                openai_tools = tool.to_openai_tool()
                if isinstance(openai_tools, list):
                    for t in openai_tools:
                        if isinstance(t, dict) and 'function' in t and 'name' in t['function']:
                            tool_names.append(t['function']['name'])
                elif isinstance(openai_tools, dict) and 'function' in openai_tools:
                    tool_names.append(openai_tools['function']['name'])
        except (AttributeError, KeyError, TypeError) as e:
            logging.warning(f"Could not extract tool name from {tool}: {e}")
            continue
    
    if tool_names:
        system_prompt += f"\n\nYou have access to the following tools: {', '.join(tool_names)}. Use these tools when appropriate to help complete your tasks. Always use tools when they can help provide accurate information or perform actions."
```

### 2. Tool Choice Parameter (llm.py) - IMPROVED
For Gemini models, we now set `tool_choice='auto'` with better model detection and support checking:

```python
# In _build_completion_params method with enhanced model detection
if 'tools' in params and params['tools'] and 'tool_choice' not in params:
    # More comprehensive Gemini model detection
    if any(prefix in self.model.lower() for prefix in ['gemini', 'gemini/', 'google/gemini']):
        try:
            import litellm
            # Check if model supports function calling before setting tool_choice
            if litellm.supports_function_calling(model=self.model):
                params['tool_choice'] = 'auto'
        except Exception as e:
            # If check fails, still set tool_choice for known Gemini models
            logging.debug(f"Could not verify function calling support: {e}. Setting tool_choice anyway.")
            params['tool_choice'] = 'auto'
```

## Testing the Fix

To test the fix, use the following code:

```python
import asyncio
from praisonaiagents import Agent, Task, PraisonAIAgents

# Define a simple tool
async def search_tool(query: str) -> str:
    """Search for information on the internet"""
    return f"Search results for: {query}"

# Create agent with Gemini model
agent = Agent(
    name="SearchAgent",
    role="Information Researcher",
    goal="Find accurate information using search tools",
    backstory="Expert at finding and analyzing information",
    tools=[search_tool],
    llm={"model": "gemini/gemini-1.5-flash-8b"}
)

# Create task
task = Task(
    description="Search for information about AI breakthroughs in 2024",
    expected_output="Summary of AI breakthroughs",
    agent=agent
)

# Run
async def test():
    agents = PraisonAIAgents(agents=[agent], tasks=[task])
    result = await agents.astart()
    print(result)

asyncio.run(test())
```

## Improvements Made to Original PR

1. **Enhanced Error Handling**: Added try-catch blocks to prevent crashes from malformed tools
2. **MCP Tool Support**: Now properly extracts names from tools with `to_openai_tool` method  
3. **Better Model Detection**: More comprehensive Gemini model detection including variants like 'google/gemini'
4. **Function Calling Support Check**: Uses litellm's `supports_function_calling` to verify model capabilities
5. **Type Safety**: Added isinstance checks to prevent TypeErrors when accessing nested dictionaries

## Backward Compatibility
- The fix only adds to existing functionality without modifying core behavior
- Tools continue to work exactly as before for all other models
- The system prompt enhancement only occurs when tools are present
- The tool_choice parameter is only added for Gemini models
- All error handling is non-breaking with appropriate logging

## Additional Recommendations

If issues persist with specific models:

1. **Explicit Tool Instructions in Task Description**:
   ```python
   task = Task(
       description="Use the tavily_search tool to find information about AI breakthroughs",
       # ... rest of task config
   )
   ```

2. **Use OpenAI Models for Tool-Heavy Tasks**:
   OpenAI models (gpt-4, gpt-4o) have better native tool calling support.

3. **Debug Tool Registration**:
   Enable debug logging to see tool registration:
   ```python
   import logging
   logging.basicConfig(level=logging.DEBUG)
   ```

## Verification Steps

1. Check that tools are properly formatted by the agent
2. Verify the system prompt includes tool instructions
3. Confirm tool_choice is set for Gemini models
4. Monitor LLM responses for tool_calls in the response

The fix ensures that Gemini models are properly instructed to use available tools, resolving the issue where agents would claim they don't have internet access despite having search tools available.