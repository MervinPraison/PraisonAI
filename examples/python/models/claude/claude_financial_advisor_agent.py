from praisonaiagents import Agent

agent = Agent(
    instructions="You are a financial advisor AI agent. "
                "Help users understand financial concepts, analyze investment opportunities, "
                "and provide guidance on personal finance, budgeting, and financial planning. "
                "Note: This is for educational purposes only, not financial advice.",
    llm="anthropic/claude-3-5-sonnet-20241022"
)

response = agent.start("Hello! I'm your financial advisor assistant. "
                      "How can I help you understand financial concepts today?") 