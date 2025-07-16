from praisonaiagents import Agent

agent = Agent(
    instructions="You are an investment advisor AI agent. Help users with investment strategies, portfolio analysis, risk assessment, and market insights.",
    llm="xai/grok-4"
)

response = agent.start("I have $50,000 to invest. What would be a good diversified portfolio for someone in their 30s?") 