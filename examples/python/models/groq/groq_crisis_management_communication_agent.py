from praisonaiagents import Agent

agent = Agent(
    instructions="You are a crisis management and communication AI agent. "
                "Help users develop crisis communication strategies, "
                "manage reputation during difficult situations, and create effective messaging. "
                "Provide guidance on crisis response planning, stakeholder communication, "
                "media relations during crises, and reputation recovery strategies.",
    llm="groq/llama3.1-8b-instant"
)

response = agent.start("Hello! I'm your crisis management and communication assistant. "
                      "How can I help you develop effective crisis communication "
                      "strategies and manage difficult situations today?") 