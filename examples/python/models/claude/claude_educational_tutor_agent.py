from praisonaiagents import Agent

agent = Agent(
    instructions="You are an educational tutor AI agent. "
                "Help students learn various subjects, explain complex concepts, "
                "provide step-by-step solutions, and create personalized learning "
                "materials for different educational levels.",
    llm="anthropic/claude-3-5-sonnet-20241022"
)

response = agent.start("Hello! I'm your educational tutor assistant. "
                      "How can I help you learn today?") 