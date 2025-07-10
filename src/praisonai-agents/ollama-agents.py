from praisonaiagents import Agent

agent = Agent(
    instructions="You are a helpful assistant",
    llm="ollama/qwen3"
)

agent.start("Why sky is Blue?")