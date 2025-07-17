from praisonaiagents import Agent

agent = Agent(
    instructions="You are a product manager AI agent. "
                "Help users with product strategy, feature prioritization, "
                "user research analysis, and product roadmap planning. Provide "
                "guidance on market analysis, competitive positioning, and user experience.",
    llm="openai/gpt-4o"
)

response = agent.start("Hello! I'm your product manager assistant. "
                      "How can I help you with your product strategy today?") 