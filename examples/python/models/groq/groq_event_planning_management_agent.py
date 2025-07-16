from praisonaiagents import Agent

agent = Agent(
    instructions="You are an event planning and management AI agent. "
                "Help users plan, organize, and manage successful events of all types. "
                "Provide guidance on venue selection, budgeting, vendor coordination, "
                "timeline management, marketing strategies, and post-event analysis. "
                "Assist with both virtual and in-person event planning.",
    llm="groq/llama3.1-8b-instant"
)

response = agent.start("Hello! I'm your event planning and management assistant. "
                      "How can I help you plan and organize your next successful "
                      "event today?") 