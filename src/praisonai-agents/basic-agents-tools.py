from praisonaiagents import Agent

def get_weather(city: str) -> str:
    return f"The weather in {city} is sunny"

agent = Agent(
    instructions="You are a helpful assistant",
    tools=[get_weather],
    output="status"
)

agent.start("What is the weather in Tokyo?")