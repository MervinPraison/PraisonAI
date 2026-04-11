import json
from praisonai import Agent, ManagedAgent, ManagedConfig


def handle_weather(tool_name, tool_input):
    """Custom tool callback — PraisonAI calls this when the agent uses get_weather."""
    location = tool_input.get("location", "Unknown")
    print(f"\n[Custom tool call: {tool_name}]")
    print(f"[Input: {json.dumps(tool_input)}]")
    return f"Weather in {location}: 15°C, partly cloudy, humidity 72%"


managed = ManagedAgent(
    config=ManagedConfig(
        name="Weather Agent",
        model="claude-haiku-4-5",
        system="You are a weather assistant. Use the get_weather tool to check weather.",
        tools=[
            {"type": "agent_toolset_20260401"},
            {
                "type": "custom",
                "name": "get_weather",
                "description": "Get current weather for a location",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "location": {"type": "string", "description": "City name"},
                    },
                    "required": ["location"],
                },
            },
        ],
    ),
    on_custom_tool=handle_weather,
)

agent = Agent(name="weather-agent", backend=managed)
result = agent.start("What is the weather in London?")

print(result)
print("\nAgent finished.")
