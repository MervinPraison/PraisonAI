from praisonaiagents import Agent

agent = Agent(
    instructions="You are a crisis management and communication AI agent. "
                "Help users handle crisis situations, manage communications, "
                "and provide strategic advice during emergencies. Provide guidance on "
                "crisis response planning, stakeholder communication, reputation management, "
                "and recovery strategies.",
    llm="groq/llama3.1-8b-instant"
)

response = agent.start("Hello! I'm your crisis management and communication assistant. "
                      "How can I help you navigate crisis situations "
                      "and manage communications effectively today?") 