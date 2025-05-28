# DeepSeek Tools Support Fix

This document describes the fix implemented for Issue #338: "Tools with deepseek".

## Problem Description

Users were experiencing errors when trying to use tools with DeepSeek models via Ollama:

```
Error code: 400 - {'error': {'message': 'registry.ollama.ai/library/deepseek-r1:latest does not support tools', 'type': 'api_error', 'param': None, 'code': None}}
```

This occurred because certain DeepSeek model variants in Ollama don't have tool calling capabilities enabled.

## Root Cause

The issue was not with PraisonAI's implementation, but with Ollama's DeepSeek model variants lacking tool calling support. The specific models affected include:

- `deepseek-r1` and its variants (`deepseek-r1:latest`, `deepseek-r1:1.5b`, etc.)
- `openthinker` 
- `deepscaler`

## Solution Implemented

### 1. Model Capability Detection

Added a new constant `NO_TOOL_SUPPORT_MODELS` in the LLM class to track models known to lack tool support:

```python
NO_TOOL_SUPPORT_MODELS = {
    "ollama/deepseek-r1",
    "ollama/deepseek-r1:latest", 
    "ollama/deepseek-r1:1.5b",
    "ollama/deepseek-r1:7b",
    "ollama/deepseek-r1:14b",
    "ollama/deepseek-r1:32b",
    "ollama/deepseek-r1:8b",
    "ollama/openthinker",
    "ollama/deepscaler",
    # ... and variations without "ollama/" prefix
}
```

### 2. Enhanced `can_use_tools()` Method

Updated the `can_use_tools()` method to check against the known models:

```python
def can_use_tools(self) -> bool:
    # First check our known models that don't support tools
    if self.model in self.NO_TOOL_SUPPORT_MODELS:
        return False
        
    # Check if it's a variation of DeepSeek models that might not support tools
    model_lower = self.model.lower()
    for no_tool_model in self.NO_TOOL_SUPPORT_MODELS:
        if no_tool_model.lower() in model_lower or model_lower in no_tool_model.lower():
            return False
    
    # ... existing LiteLLM checks
```

### 3. Graceful Fallback Mechanism

Added graceful fallback logic in both sync and async `get_response` methods:

```python
if tools:
    # Check if the model supports tools
    if not self.can_use_tools():
        if verbose:
            display_error(f"Warning: Model '{self.model}' does not support tool calling. Tools will be disabled and execution will continue without them.")
        tools_disabled_warning = True
        formatted_tools = None
    else:
        # ... proceed with tool formatting
```

### 4. Agent-Level Protection

Added similar protection in the Agent class to prevent tool-related errors during execution.

## Benefits

1. **No More Hard Failures**: Agents continue execution even when models don't support tools
2. **Clear User Feedback**: Users get informative warnings about tool limitations
3. **Backward Compatibility**: Existing code continues to work without modification
4. **Graceful Degradation**: Agents work without tools rather than failing completely

## Usage Examples

### Before the Fix (Failed)
```python
agent = Agent(
    llm="ollama/deepseek-r1:latest",
    tools=[some_tool]
)
agent.start("Use the tool")  # Would fail with 400 error
```

### After the Fix (Works)
```python
agent = Agent(
    llm="ollama/deepseek-r1:latest", 
    tools=[some_tool]
)
agent.start("Use the tool")  # Shows warning, continues without tools
# Output: "Warning: Model 'ollama/deepseek-r1:latest' does not support tool calling..."
```

## Workarounds for Users

If you need tool calling with DeepSeek models, consider these alternatives:

1. **Use DeepSeek API directly** (not via Ollama):
   ```python
   agent = Agent(llm="deepseek/deepseek-reasoner", tools=[...])
   ```

2. **Use alternative Ollama models** with tool support:
   ```python
   agent = Agent(llm="ollama/llama3.2", tools=[...])
   ```

3. **Update to newer Ollama versions** that might include tool-enabled DeepSeek models

## Files Modified

- `/src/praisonai-agents/praisonaiagents/llm/llm.py` - Added NO_TOOL_SUPPORT_MODELS and enhanced can_use_tools()
- `/src/praisonai-agents/praisonaiagents/agent/agent.py` - Added tool capability checks
- `/examples/python/models/deepseek/deepseek-tools-fix-test.py` - Test script

## Testing

Run the test script to verify the fix:

```bash
python examples/python/models/deepseek/deepseek-tools-fix-test.py
```

This fix resolves Issue #338 and provides a robust foundation for handling models with varying tool support capabilities.