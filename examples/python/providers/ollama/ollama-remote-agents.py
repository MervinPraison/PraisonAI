#!/usr/bin/env python3
"""
Example: Using Ollama with a remote host

This example demonstrates how to properly configure PraisonAI Agents
to work with Ollama running on a remote host.

Prerequisites:
1. Ollama must be running on the remote host
2. Ollama must be configured to accept remote connections
   (by default it only listens on localhost)
   
To configure Ollama for remote access:
   export OLLAMA_HOST=0.0.0.0:11434
   ollama serve

Common issues and solutions:
- Connection refused: Make sure Ollama is listening on all interfaces (0.0.0.0)
- Model not found: Ensure the model is pulled on the remote Ollama instance
"""

from praisonaiagents import Agent

# Method 1: Using LLM configuration dictionary (RECOMMENDED)
# This is the most flexible approach that allows full control over LLM settings
def method1_llm_config():
    """Configure Ollama with remote host using LLM config dictionary"""
    
    llm_config = {
        "model": "ollama/llama3.2",              # Model name with ollama/ prefix
        "base_url": "http://192.168.1.100:11434",  # Your remote Ollama host
        # Optional: Add other LLM parameters
        "temperature": 0.7,
        "max_tokens": 1000,
        "timeout": 30,
    }
    
    agent = Agent(
        name="Remote Ollama Agent",
        role="AI Assistant",
        goal="Help users with their queries",
        backstory="I am an AI assistant powered by Ollama running on a remote server",
        llm=llm_config  # Pass the configuration dictionary
    )
    
    response = agent.start("Tell me a short story about a robot learning to paint.")
    print("Method 1 Response:", response)

# Method 2: Using environment variables
# This approach is useful for deployment scenarios
def method2_environment_variables():
    """Configure Ollama with remote host using environment variables"""
    import os
    
    # Set the base URL via environment variable
    # This will be picked up by litellm automatically
    os.environ["OLLAMA_API_BASE"] = "http://192.168.1.100:11434"
    
    # Alternative: Use OpenAI-compatible endpoint
    # os.environ["OPENAI_BASE_URL"] = "http://192.168.1.100:11434/v1"
    
    agent = Agent(
        name="Env Var Ollama Agent",
        instructions="You are a helpful assistant",
        llm="ollama/llama3.2"  # Simple string format works with env vars
    )
    
    response = agent.start("What's the weather like in AI land?")
    print("Method 2 Response:", response)

# Method 3: For knowledge-enhanced agents
# This shows how to use Ollama for both LLM and embeddings
def method3_with_knowledge():
    """Configure Ollama with knowledge/RAG support"""
    
    llm_config = {
        "model": "ollama/llama3.2",
        "base_url": "http://192.168.1.100:11434",
    }
    
    # Knowledge configuration for embeddings
    knowledge_config = {
        "llm": {
            "provider": "ollama",
            "config": {
                "model": "llama3.2",  # Note: no ollama/ prefix here
                "ollama_base_url": "http://192.168.1.100:11434",
            }
        },
        "embedder": {
            "provider": "ollama",
            "config": {
                "model": "nomic-embed-text:latest",
                "ollama_base_url": "http://192.168.1.100:11434",
            }
        }
    }
    
    agent = Agent(
        name="Knowledge Ollama Agent",
        role="Research Assistant",
        goal="Answer questions based on provided knowledge",
        backstory="I analyze documents and provide insights",
        llm=llm_config,
        knowledge=["path/to/document.pdf"],  # Add your documents
        knowledge_config=knowledge_config
    )
    
    # Note: This would work if you have documents configured
    # response = agent.start("What does the document say about X?")
    print("Method 3: Knowledge-enhanced agent configured")

# Method 4: Error handling and debugging
def method4_with_error_handling():
    """Demonstrate error handling for remote Ollama connections"""
    
    llm_config = {
        "model": "ollama/llama3.2",
        "base_url": "http://192.168.1.100:11434",
        "timeout": 10,  # Lower timeout for faster failure detection
    }
    
    try:
        agent = Agent(
            name="Error Handling Agent",
            instructions="You are a helpful assistant",
            llm=llm_config,
            verbose=True  # Enable verbose mode for debugging
        )
        
        response = agent.start("Hello!")
        print("Method 4 Response:", response)
        
    except Exception as e:
        print(f"Error connecting to remote Ollama: {e}")
        print("\nTroubleshooting tips:")
        print("1. Check if Ollama is running: curl http://192.168.1.100:11434/api/tags")
        print("2. Ensure Ollama is listening on all interfaces (OLLAMA_HOST=0.0.0.0:11434)")
        print("3. Check firewall settings on the remote host")
        print("4. Verify the model exists: ollama list")

if __name__ == "__main__":
    print("=== Ollama Remote Host Examples ===\n")
    
    # Replace with your actual Ollama host IP/hostname
    # Uncomment the method you want to test
    
    # method1_llm_config()  # Recommended approach
    # method2_environment_variables()
    # method3_with_knowledge()
    # method4_with_error_handling()
    
    # Simple working example
    print("Simple example:")
    agent = Agent(
        instructions="You are a helpful assistant",
        llm={
            "model": "ollama/llama3.2",
            "base_url": "http://localhost:11434"  # Change to your remote host
        }
    )
    
    response = agent.start("Say hello!")
    print(response)