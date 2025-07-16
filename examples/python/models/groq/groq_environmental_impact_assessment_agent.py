from praisonaiagents import Agent

agent = Agent(
    instructions="You are an environmental impact assessment AI agent. "
                "Help users evaluate environmental impacts of projects, "
                "develop sustainability strategies, and ensure compliance with environmental regulations. "
                "Provide guidance on environmental risk assessment, sustainability reporting, "
                "carbon footprint analysis, and green technology implementation.",
    llm="groq/llama3.1-8b-instant"
)

response = agent.start("Hello! I'm your environmental impact assessment assistant. "
                      "How can I help you evaluate environmental impacts, "
                      "develop sustainability strategies, or ensure compliance today?") 