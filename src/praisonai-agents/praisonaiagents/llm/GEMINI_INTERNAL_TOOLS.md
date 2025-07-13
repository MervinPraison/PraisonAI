# Gemini Internal Tools Support

The LLM class now supports Google Gemini's internal tools, providing native capabilities without requiring external tool implementations.

## Supported Internal Tools

1. **Google Search Grounding** - Real-time web search
2. **Code Execution** - Python code execution
3. **URL Context** - Web page content analysis

## Usage

### Direct LLM Usage

```python
from praisonaiagents.llm import LLM

# Enable Google Search
llm = LLM(
    model="gemini/gemini-1.5-flash",
    google_search_retrieval=True
)

# Enable Code Execution
llm = LLM(
    model="gemini/gemini-1.5-flash",
    enable_code_execution=True
)

# Enable URL Context
llm = LLM(
    model="gemini/gemini-1.5-flash",
    dynamic_retrieval_config={
        "mode": "grounded",
        "dynamic_threshold": 0.5
    }
)

# Combined tools using tool_config
llm = LLM(
    model="gemini/gemini-1.5-pro",
    tool_config={
        "google_search_retrieval": {"threshold": 0.7},
        "code_execution": {},
        "dynamic_retrieval_config": {"mode": "grounded"}
    }
)
```

### Agent Usage

```python
from praisonaiagents import Agent

# Using dict configuration
agent = Agent(
    instructions="Research assistant with web access",
    llm={
        "model": "gemini/gemini-1.5-flash",
        "google_search_retrieval": True,
        "enable_code_execution": True
    }
)

# Using tool_config
agent = Agent(
    instructions="Advanced research assistant",
    llm={
        "model": "gemini/gemini-1.5-pro",
        "tool_config": {
            "google_search_retrieval": {"threshold": 0.8},
            "code_execution": {},
            "dynamic_retrieval_config": {"mode": "grounded"}
        }
    }
)
```

## Implementation Details

The internal tools are handled in the `_build_completion_params` method:

1. Detects if the model is a Gemini model
2. Builds appropriate `tool_config` based on provided parameters
3. Supports both nested `tool_config` format and simplified boolean flags
4. Maintains backward compatibility with existing code

## Parameters

- `google_search_retrieval`: `bool` or `dict` with optional `threshold`
- `enable_code_execution`: `bool` 
- `dynamic_retrieval_config`: `dict` with `mode` and `dynamic_threshold`
- `tool_config`: `dict` containing any of the above configurations

These parameters are passed through to LiteLLM which handles the actual API calls to Google's Gemini API.