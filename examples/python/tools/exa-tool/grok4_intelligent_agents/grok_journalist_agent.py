from praisonaiagents import Agent

agent = Agent(
    instructions="You are a journalist AI agent. Help with news writing, article creation, fact-checking, and content generation for various media platforms.",
    llm="xai/grok-4"
)

response = agent.start("I need to write an article about the latest developments in renewable energy. Can you help me structure it?") 