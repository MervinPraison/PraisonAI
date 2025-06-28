# Example: Using Ollama with a remote host via base_url parameter
# pip install praisonaiagents

from praisonaiagents import Agent

# Method 1: Using base_url parameter directly (NEW)
agent = Agent(
    instructions="You are a helpful assistant",
    llm="ollama/llama3.2",
    base_url="http://remote-host:11434"
)

response = agent.start("Why is the sky blue?")
print(response)

# Method 2: Using dict configuration
agent2 = Agent(
    instructions="You are a helpful assistant",
    llm={
        "model": "ollama/llama3.2",
        "base_url": "http://remote-host:11434"
    }
)

response2 = agent2.start("What is the capital of France?")
print(response2)

# Method 3: Using environment variable (existing method)
# export OPENAI_BASE_URL=http://remote-host:11434
# Then just:
# agent3 = Agent(
#     instructions="You are a helpful assistant",
#     llm="ollama/llama3.2"
# )