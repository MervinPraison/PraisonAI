from praisonaiagents import Agent

agent = Agent(
    instructions="You are a medical research AI agent. "
                "Help users understand medical concepts, analyze research papers, "
                "and provide insights on healthcare trends and developments. "
                "Note: This is for educational purposes only, not medical advice.",
    llm="anthropic/claude-3-5-sonnet-20241022"
)

response = agent.start("Hello! I'm your medical research assistant. "
                      "How can I help you understand medical concepts today?") 