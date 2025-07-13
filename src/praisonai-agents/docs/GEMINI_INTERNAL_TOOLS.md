# Gemini Internal Tools Guide

This guide explains how to use Google Gemini's internal tools with PraisonAI Agents. These tools provide native capabilities without requiring external tool implementations.

## Overview

Gemini models provide three powerful internal tools:

1. **Google Search Grounding** - Real-time web search capabilities
2. **Code Execution** - Write and execute Python code
3. **URL Context (Dynamic Retrieval)** - Analyze and extract content from URLs

## Prerequisites

- PraisonAI Agents with LLM support: `pip install "praisonaiagents[llm]"`
- A valid Google AI API key (set as `GOOGLE_API_KEY` environment variable)
- Gemini model access (e.g., `gemini-1.5-flash`, `gemini-1.5-pro`)

## Basic Usage

### 1. Google Search Grounding

Enable web search capabilities for current information:

```python
from praisonaiagents import Agent

# Simple boolean flag
search_agent = Agent(
    instructions="You are a helpful assistant that searches the web.",
    llm={
        "model": "gemini/gemini-1.5-flash",
        "google_search_retrieval": True
    }
)

# With threshold configuration
search_agent = Agent(
    instructions="You are a research assistant.",
    llm={
        "model": "gemini/gemini-1.5-flash",
        "tool_config": {
            "google_search_retrieval": {
                "threshold": 0.7  # Confidence threshold (0.0-1.0)
            }
        }
    }
)
```

### 2. Code Execution

Enable Python code execution capabilities:

```python
# Simple boolean flag
code_agent = Agent(
    instructions="You are a coding assistant.",
    llm={
        "model": "gemini/gemini-1.5-flash",
        "enable_code_execution": True
    }
)

# Using tool_config
code_agent = Agent(
    instructions="You are a data analyst.",
    llm={
        "model": "gemini/gemini-1.5-flash",
        "tool_config": {
            "code_execution": {}
        }
    }
)
```

### 3. URL Context (Dynamic Retrieval)

Enable web page analysis:

```python
url_agent = Agent(
    instructions="You analyze web content.",
    llm={
        "model": "gemini/gemini-1.5-flash",
        "dynamic_retrieval_config": {
            "mode": "grounded",  # or "unspecified"
            "dynamic_threshold": 0.5
        }
    }
)

# Or using tool_config
url_agent = Agent(
    instructions="You analyze web content.",
    llm={
        "model": "gemini/gemini-1.5-flash",
        "tool_config": {
            "dynamic_retrieval_config": {
                "mode": "grounded",
                "dynamic_threshold": 0.5
            }
        }
    }
)
```

## Advanced Usage

### Combining Multiple Internal Tools

```python
research_agent = Agent(
    instructions="""You are an advanced research assistant that can:
    - Search the web for current information
    - Analyze content from URLs
    - Write and execute Python code
    """,
    llm={
        "model": "gemini/gemini-1.5-pro-latest",
        "temperature": 0.7,
        "max_tokens": 2000,
        "tool_config": {
            "google_search_retrieval": {
                "threshold": 0.8
            },
            "code_execution": {},
            "dynamic_retrieval_config": {
                "mode": "grounded",
                "dynamic_threshold": 0.6
            }
        }
    }
)
```

### Using with Custom Tools

You can combine Gemini's internal tools with custom tool functions:

```python
def get_weather(city: str) -> str:
    """Get weather for a city"""
    return f"The weather in {city} is sunny"

hybrid_agent = Agent(
    instructions="You can use both custom and internal tools.",
    llm={
        "model": "gemini/gemini-1.5-flash",
        "google_search_retrieval": True,
        "enable_code_execution": True
    },
    tools=[get_weather]  # Custom tools work alongside internal tools
)
```

### Async Support

All internal tools work with async operations:

```python
import asyncio

async def main():
    agent = Agent(
        instructions="Research assistant",
        llm={
            "model": "gemini/gemini-1.5-flash",
            "google_search_retrieval": True,
            "enable_code_execution": True
        }
    )
    
    response = await agent.astart("Search for Python news and write code to parse it")
    print(response)

asyncio.run(main())
```

## Use Cases

### Financial Analysis
```python
analyst = Agent(
    instructions="You are a financial analyst.",
    llm={
        "model": "gemini/gemini-1.5-pro",
        "tool_config": {
            "google_search_retrieval": {"threshold": 0.9},
            "code_execution": {}
        }
    }
)

response = analyst.start("""
1. Search for the current S&P 500 value
2. Write code to calculate its year-to-date performance
3. Create a simple visualization
""")
```

### Content Research
```python
researcher = Agent(
    instructions="You are a content researcher.",
    llm={
        "model": "gemini/gemini-1.5-flash",
        "tool_config": {
            "google_search_retrieval": {"threshold": 0.7},
            "dynamic_retrieval_config": {
                "mode": "grounded",
                "dynamic_threshold": 0.5
            }
        }
    }
)

response = researcher.start("""
Research the latest trends in renewable energy.
If you find interesting articles, analyze their content in detail.
""")
```

### Data Science Tasks
```python
data_scientist = Agent(
    instructions="You are a data scientist.",
    llm={
        "model": "gemini/gemini-1.5-pro",
        "enable_code_execution": True
    }
)

response = data_scientist.start("""
1. Generate a synthetic dataset with 1000 samples
2. Perform exploratory data analysis
3. Build a simple linear regression model
4. Evaluate the model and show results
""")
```

## Configuration Parameters

### Google Search Grounding
- `google_search_retrieval`: `bool` or `dict`
  - When `True`: Enables with default settings
  - When `dict`: Can specify `threshold` (float 0.0-1.0)

### Code Execution
- `enable_code_execution`: `bool`
  - When `True`: Enables Python code execution
- Alternative: `tool_config.code_execution`: `dict` (empty dict enables it)

### URL Context
- `dynamic_retrieval_config`: `dict`
  - `mode`: `"grounded"` or `"unspecified"`
  - `dynamic_threshold`: float (0.0-1.0)

### Tool Config Format
All tools can be configured via the `tool_config` parameter:

```python
llm={
    "model": "gemini/gemini-1.5-pro",
    "tool_config": {
        "google_search_retrieval": {...},
        "code_execution": {...},
        "dynamic_retrieval_config": {...}
    }
}
```

## Best Practices

1. **Model Selection**: Use `gemini-1.5-pro` for complex tasks requiring multiple tools
2. **Thresholds**: Adjust thresholds based on accuracy vs. coverage needs
3. **Error Handling**: Internal tools may fail; ensure your prompts handle edge cases
4. **Context Length**: Be mindful of context limits when using URL retrieval
5. **Rate Limits**: Google Search has rate limits; implement appropriate delays

## Limitations

1. **Model Support**: Not all Gemini models support all internal tools
2. **API Quotas**: Subject to Google AI API quotas and limits
3. **Code Execution**: Limited to Python, with security restrictions
4. **URL Access**: Some websites may block or limit access
5. **Search Results**: Limited to what Google Search provides

## Troubleshooting

### Common Issues

1. **"Tool not supported" error**
   - Ensure you're using a compatible Gemini model
   - Check that your API key has appropriate permissions

2. **Empty search results**
   - Try adjusting the threshold parameter
   - Ensure your search queries are specific

3. **Code execution failures**
   - Code execution has security limits
   - Avoid system calls or file operations

4. **URL retrieval issues**
   - Some sites block automated access
   - Try alternative URLs or sources

## Migration from External Tools

If you're currently using external search/code tools, migration is simple:

```python
# Before (external tools)
from web_search_tool import search_web
agent = Agent(
    instructions="...",
    llm="gemini/gemini-1.5-flash",
    tools=[search_web]
)

# After (internal tools)
agent = Agent(
    instructions="...",
    llm={
        "model": "gemini/gemini-1.5-flash",
        "google_search_retrieval": True
    }
)
```

## Future Enhancements

As Google adds more internal tools to Gemini, they can be accessed by:
1. Adding the tool configuration to `tool_config`
2. Using any new simplified parameters that LiteLLM supports

Check the [Google AI documentation](https://ai.google.dev/gemini-api/docs) for the latest available tools.