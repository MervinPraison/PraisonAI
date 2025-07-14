from praisonaiagents import Agent

agent = Agent(
    instructions="You are an AI services agency agent. "
                 "Help users with comprehensive business services including marketing, "
                 "content creation, strategy, and operational optimization using CrewAI framework.",
    llm="xai/grok-4"
)

response = agent.start(
    "I need help with my startup's marketing strategy and content creation. "
    "Can you provide a comprehensive plan?"
) 