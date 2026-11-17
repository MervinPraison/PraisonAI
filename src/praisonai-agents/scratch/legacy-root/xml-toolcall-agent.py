from praisonaiagents import Agent

def get_weather(city: str) -> str:
    return f"The weather in {city} is sunny"

agent = Agent(
    instructions="You are a helpful assistant",
    llm="openrouter/qwen/qwen2.5-vl-72b-instruct",
    tools=[get_weather]
)

agent.start("What is the weather in Tokyo?")