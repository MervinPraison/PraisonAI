from praisonaiagents import Agent

agent = Agent(
    instructions="You are a self-evolving AI agent. "
                "Continuously learn from interactions, adapt your responses, and improve your capabilities. "
                "Help users with complex problem-solving, creative tasks, and provide insights that evolve based on context and user needs.",
    llm="openrouter/moonshotai/kimi-k2"
)

response = agent.start("Hello! I'm your self-evolving AI assistant. "
                      "How can I help you today, and how can I learn and improve from our interaction?") 