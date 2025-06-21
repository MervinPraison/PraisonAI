import os

# Set OpenAI API configuration BEFORE importing praisonaiagents
# os.environ["OPENAI_API_BASE"] = "http://localhost:1234/v1"
# os.environ["OPENAI_API_KEY"] = "not-needed"

# Now import after setting the environment
from praisonaiagents import Agent, MCP

# Paths to python and the weather server script
python_path = os.getenv("PYTHON_PATH", "python")
server_path = os.getenv("WEATHER_SERVER_PATH", "weather_server.py")

# Create the agent with Ollama
weather_agent = Agent(
    name="Weather Assistant",
    role="Weather assistant",
    goal="Provide accurate and timely weather information for various cities",
    instructions="""
You are a helpful weather assistant that can provide current weather information,
forecasts, and weather comparisons for different cities. Use the available weather tools to answer
user questions about weather conditions. You can:

- Get current weather for cities
- Get hourly forecasts 
- Compare weather between two cities
- Use both mock data and real API data (when API key is provided)
- Set use_real_api True to use real API data all the time

Always use the appropriate weather tools when users ask about weather information.
""",
    llm="ollama/llama3.2",  # Using Ollama with llama3.2
    tools=MCP(f"{python_path} {server_path}"),
    verbose=True
)

# Optional: run a sample task
response = weather_agent.start("What's the weather in London?")
print(response)
