"""
Example 9: Streaming with Tools

Streaming works with tool-enabled agents. The agent streams
its response while tool calls are handled internally.

When to use: When you have agents with tools and want streaming output.
"""
from praisonaiagents import Agent

def get_weather(city: str) -> str:
    """Get weather for a city."""
    return f"Weather in {city}: Sunny, 72°F"

def get_time(timezone: str = "UTC") -> str:
    """Get current time in timezone."""
    import datetime
    return f"Current time ({timezone}): {datetime.datetime.now().strftime('%H:%M:%S')}"

agent = Agent(
    name="WeatherBot",
    instructions="You help with weather and time queries. Use tools when asked.",
    tools=[get_weather, get_time],
    output="stream"
)

print("Streaming with tools:")
print("-" * 40)

for chunk in agent.start("What's the weather in Tokyo and the current time?"):
    print(chunk, end="", flush=True)

print("\n" + "-" * 40)
