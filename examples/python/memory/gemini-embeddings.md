# Gemini Embedding Support in PraisonAI

This document describes how to use Google's Gemini embedding models with PraisonAI's memory system.

## Overview

PraisonAI now supports configurable embedding models through LiteLLM, including Google's Gemini embedding models. This allows you to use models like `text-embedding-004` or `gemini-embedding-exp-03-07` for semantic search and memory storage.

## Configuration

### Default Configuration (OpenAI)

By default, PraisonAI uses OpenAI's `text-embedding-3-small` model:

```python
from praisonaiagents import PraisonAIAgents

agents = PraisonAIAgents(
    agents=[...],
    tasks=[...],
    memory=True  # Uses default OpenAI embeddings
)
```

### Using Gemini Embeddings

To use Gemini embeddings, configure the `embedder` parameter:

```python
from praisonaiagents import PraisonAIAgents

agents = PraisonAIAgents(
    agents=[...],
    tasks=[...],
    memory=True,
    embedder={
        "provider": "gemini",
        "config": {
            "model": "text-embedding-004"  # or "gemini-embedding-exp-03-07"
        }
    }
)
```

## Prerequisites

1. **API Key**: Set your Google API key:
   ```bash
   export GOOGLE_API_KEY='your-api-key'
   ```

2. **Dependencies**: Ensure you have the memory dependencies installed:
   ```bash
   pip install "praisonaiagents[memory]"
   ```

## Supported Models

### Gemini Embedding Models

- `text-embedding-004` - Stable embedding model
- `gemini-embedding-exp-03-07` - Experimental model with advanced features

### Task Types (Optional)

Gemini models support task-specific optimizations:
- `SEMANTIC_SIMILARITY`
- `CLASSIFICATION`
- `CLUSTERING`
- `RETRIEVAL_DOCUMENT`
- `RETRIEVAL_QUERY`
- `QUESTION_ANSWERING`
- `FACT_VERIFICATION`

Example with task type:
```python
embedder={
    "provider": "gemini",
    "config": {
        "model": "text-embedding-004",
        "task_type": "RETRIEVAL_DOCUMENT"
    }
}
```

## Complete Example

```python
import os
from praisonaiagents import Agent, Task, PraisonAIAgents

# Ensure Google API key is set
os.environ["GOOGLE_API_KEY"] = "your-api-key"

# Create agents
researcher = Agent(
    name="Researcher",
    role="Information Researcher",
    goal="Store information with semantic understanding",
    llm="gpt-4o-mini"
)

# Create task
task = Task(
    description="Research and store information about AI advancements",
    expected_output="Confirmation of stored information",
    agent=researcher
)

# Initialize with Gemini embeddings
agents = PraisonAIAgents(
    agents=[researcher],
    tasks=[task],
    memory=True,
    embedder={
        "provider": "gemini",
        "config": {
            "model": "text-embedding-004"
        }
    }
)

# Run the agents
agents.start()
```

## Backward Compatibility

The implementation maintains full backward compatibility:

1. **No embedder config**: Uses default OpenAI `text-embedding-3-small`
2. **Existing configs**: Continue to work without modification
3. **Other providers**: Supports any embedding model available through LiteLLM

## Memory Configuration with Mem0

When using Mem0 as the memory provider, the embedder configuration is passed through:

```python
memory_config = {
    "provider": "mem0",
    "config": {
        "api_key": "your-mem0-key",
        "embedder": {
            "provider": "gemini",
            "config": {
                "model": "text-embedding-004"
            }
        }
    }
}
```

## Troubleshooting

1. **API Key Error**: Ensure `GOOGLE_API_KEY` is set in your environment
2. **Model Not Found**: Verify the model name is correct
3. **LiteLLM Error**: Ensure litellm is installed and up to date
4. **Embedding Size Mismatch**: When switching models, you may need to clear the vector database as different models produce different embedding dimensions

## See Also

- [Gemini API Documentation](https://ai.google.dev/gemini-api/docs/embeddings)
- [LiteLLM Embedding Models](https://docs.litellm.ai/docs/embedding/supported_embedding)
- Example: `/examples/python/memory/gemini-embedding-example.py`
