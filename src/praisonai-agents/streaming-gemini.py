from praisonaiagents import Agent

agent = Agent(
    instructions="You are a helpful assistant",
    llm="gemini/gemini-2.5-flash"
)

# Use chat method with stream=True for streaming responses
for chunk in agent.chat("Write a short paragraph about the history of computing", stream=True):
    print(chunk, end="", flush=True)
print()  # Final newline