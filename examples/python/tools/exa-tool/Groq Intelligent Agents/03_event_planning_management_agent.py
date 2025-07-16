from praisonaiagents import Agent

agent = Agent(
    instructions="You are an event planning and management AI agent. "
                "Help users plan and manage successful events, from small gatherings "
                "to large-scale conferences. Provide guidance on venue selection, "
                "budget management, vendor coordination, timeline planning, "
                "and event marketing strategies.",
    llm="groq/llama3.1-8b-instant"
)

response = agent.start("Hello! I'm your event planning and management assistant. "
                      "How can I help you create and execute successful "
                      "events today?") 