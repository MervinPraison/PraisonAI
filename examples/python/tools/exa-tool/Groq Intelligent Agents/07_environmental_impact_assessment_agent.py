from praisonaiagents import Agent

agent = Agent(
    instructions="You are an environmental impact assessment AI agent. "
                "Help users analyze environmental impacts, assess sustainability metrics, "
                "and ensure compliance with environmental regulations. Provide guidance on "
                "carbon footprint analysis, sustainability reporting, environmental compliance, "
                "and green initiatives.",
    llm="groq/llama3.1-8b-instant"
)

response = agent.start("Hello! I'm your environmental impact assessment assistant. "
                      "How can I help you analyze environmental impacts "
                      "and ensure sustainability compliance today?") 