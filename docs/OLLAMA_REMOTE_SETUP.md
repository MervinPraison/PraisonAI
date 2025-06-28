# Using Ollama with Remote Hosts in PraisonAI

This guide explains how to configure PraisonAI Agents to work with Ollama running on a remote host.

## Quick Start

To use Ollama on a remote host, pass the `base_url` through the `llm` configuration dictionary:

```python
from praisonaiagents import Agent

agent = Agent(
    name="My Agent",
    llm={
        "model": "ollama/llama3.2",
        "base_url": "http://192.168.1.100:11434"  # Your Ollama host
    }
)

response = agent.start("Hello, how are you?")
```

## Common Mistakes to Avoid

### ❌ Wrong: Passing base_url directly to Agent
```python
# This will raise: TypeError: Agent.__init__() got an unexpected keyword argument 'base_url'
agent = Agent(
    name="My Agent",
    llm="ollama/llama3.2",
    base_url="http://192.168.1.100:11434"  # ❌ This doesn't work!
)
```

### ✅ Correct: Using llm configuration dictionary
```python
# Pass base_url inside the llm dictionary
agent = Agent(
    name="My Agent",
    llm={
        "model": "ollama/llama3.2",
        "base_url": "http://192.168.1.100:11434"  # ✅ This works!
    }
)
```

## Alternative Methods

### Method 1: Environment Variables

Set the Ollama API base URL using environment variables:

```bash
export OLLAMA_API_BASE=http://192.168.1.100:11434
# or
export OPENAI_BASE_URL=http://192.168.1.100:11434/v1
```

Then use the simple string format:
```python
agent = Agent(
    name="My Agent",
    llm="ollama/llama3.2"  # Will use the environment variable
)
```

### Method 2: Full LLM Configuration

For more control, you can specify additional LLM parameters:

```python
llm_config = {
    "model": "ollama/llama3.2",
    "base_url": "http://192.168.1.100:11434",
    "temperature": 0.7,
    "max_tokens": 1000,
    "timeout": 30,
    "stream": True
}

agent = Agent(
    name="My Agent",
    role="Assistant",
    goal="Help users with their queries",
    llm=llm_config
)
```

## Ollama Server Setup

Make sure your Ollama server is configured to accept remote connections:

1. **Start Ollama with network binding:**
   ```bash
   OLLAMA_HOST=0.0.0.0:11434 ollama serve
   ```

2. **Check if Ollama is accessible:**
   ```bash
   curl http://your-ollama-host:11434/api/tags
   ```

3. **Pull the required model:**
   ```bash
   ollama pull llama3.2
   ```

## Troubleshooting

### Connection Refused Error
- Ensure Ollama is listening on all interfaces (0.0.0.0) not just localhost
- Check firewall settings on the remote host
- Verify the port (default: 11434) is open

### Model Not Found Error
- Make sure the model is pulled on the remote Ollama instance
- Use `ollama list` on the remote host to see available models

### Authentication/API Key Errors
- Ollama doesn't require API keys by default
- You can pass a dummy key if needed: `"api_key": "not-required"`

## Complete Example

```python
from praisonaiagents import Agent

# Configure Ollama with error handling
try:
    agent = Agent(
        name="Remote Ollama Assistant",
        role="AI Assistant",
        goal="Provide helpful responses to user queries",
        backstory="I am powered by Ollama running on a remote server",
        llm={
            "model": "ollama/llama3.2",
            "base_url": "http://192.168.1.100:11434",
            "timeout": 30
        },
        verbose=True  # Enable for debugging
    )
    
    response = agent.start("Tell me a joke about computers")
    print(response)
    
except Exception as e:
    print(f"Error: {e}")
    print("\nTroubleshooting:")
    print("1. Is Ollama running? Check with: curl http://192.168.1.100:11434/api/tags")
    print("2. Is the model available? Check with: ollama list")
    print("3. Is Ollama configured for remote access? Use: OLLAMA_HOST=0.0.0.0:11434")
```

## Using with Knowledge/RAG

For knowledge-enhanced agents with Ollama embeddings:

```python
knowledge_config = {
    "llm": {
        "provider": "ollama",
        "config": {
            "model": "llama3.2",
            "ollama_base_url": "http://192.168.1.100:11434"
        }
    },
    "embedder": {
        "provider": "ollama",
        "config": {
            "model": "nomic-embed-text:latest",
            "ollama_base_url": "http://192.168.1.100:11434"
        }
    }
}

agent = Agent(
    name="Knowledge Agent",
    llm={
        "model": "ollama/llama3.2",
        "base_url": "http://192.168.1.100:11434"
    },
    knowledge=["document.pdf"],
    knowledge_config=knowledge_config
)
```