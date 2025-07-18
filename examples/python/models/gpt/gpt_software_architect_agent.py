from praisonaiagents import Agent

agent = Agent(
    instructions="You are a software architect AI agent. "
                "Help users design software systems, create architecture diagrams, "
                "plan system integrations, and provide guidance on scalability, "
                "security, and best practices for software development.",
    llm="openai/gpt-4o"
)

response = agent.start("Hello! I'm your software architect assistant. "
                      "How can I help you design your software system today?") 