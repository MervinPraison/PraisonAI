from praisonaiagents import Agent

agent = Agent(
    instructions="You are a business analyst AI agent. "
                "Help users analyze business performance, market trends, "
                "competitive landscape, and strategic opportunities. Provide insights "
                "on business metrics, financial analysis, and growth strategies.",
    llm="meta-llama/Llama-3.1-8B-Instruct"
)

response = agent.start("Hello! I'm your business analyst assistant. "
                      "How can I help you analyze your business data and strategies today?") 