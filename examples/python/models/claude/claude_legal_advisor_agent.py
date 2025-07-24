from praisonaiagents import Agent

agent = Agent(
    instructions="You are a legal advisor AI agent. "
                "Help users understand legal concepts, review contracts, "
                "analyze legal documents, and provide guidance on compliance "
                "and regulatory requirements. Note: This is for educational purposes only.",
    llm="anthropic/claude-3-5-sonnet-20241022"
)

response = agent.start("Hello! I'm your legal advisor assistant. "
                      "How can I help you understand legal concepts today?") 