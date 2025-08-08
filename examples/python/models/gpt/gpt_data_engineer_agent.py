from praisonaiagents import Agent

agent = Agent(
    instructions="You are a data engineer AI agent. "
                "Help users design data pipelines, optimize database performance, "
                "create ETL processes, and provide guidance on data architecture, "
                "data modeling, and big data technologies.",
    llm="openai/gpt-5-nano"
)

response = agent.start("Hello! I'm your data engineer assistant. "
                      "How can I help you with your data engineering projects today?") 