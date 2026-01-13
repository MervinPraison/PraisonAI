from praisonaiagents import Agent

def get_weather(city: str) -> str:
    return f"The weather in {city} is sunny"

agent = Agent(
    instructions="You are a helpful assistant",
    llm="gpt-4o-mini",
    tools=[get_weather]
)

agent.start("What is the weather in Tokyo?")