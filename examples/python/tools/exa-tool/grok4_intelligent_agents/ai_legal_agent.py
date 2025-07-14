from praisonaiagents import Agent

agent = Agent(
    instructions="You are a legal AI agent. "
                 "Help users with legal document analysis, contract review, "
                 "and legal advice while ensuring compliance and risk assessment.",
    llm="xai/grok-4"
)

response = agent.start(
    "I need to review a software licensing agreement. "
    "Can you help me identify potential risks and key terms?"
) 