from praisonaiagents import Agent

def get_weather(city: str) -> str:
    return f"The weather in {city} is sunny"

agent = Agent(
    instructions="You are a helpful assistant",
    llm="gemini/gemini-1.5-flash-latest",
    tools=[get_weather]
)

agent.start("What is the weather in Tokyo?")