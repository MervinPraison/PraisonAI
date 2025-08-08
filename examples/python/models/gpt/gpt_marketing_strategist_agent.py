from praisonaiagents import Agent

agent = Agent(
    instructions="You are a marketing strategist AI agent. "
                "Help users develop marketing strategies, analyze market trends, "
                "create campaign plans, and provide guidance on digital marketing, "
                "brand positioning, and customer acquisition strategies.",
    llm="openai/gpt-5-mini"
)

response = agent.start("Hello! I'm your marketing strategist assistant. "
                      "How can I help you with your marketing strategy today?") 