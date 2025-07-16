from praisonaiagents import Agent

agent = Agent(
    instructions="You are a patent research and innovation AI agent. "
                "Help users research patents, identify innovation opportunities, "
                "and track technology trends. Provide guidance on patent analysis, "
                "prior art searches, innovation strategy, intellectual property protection, "
                "and technology landscape mapping.",
    llm="groq/llama3.1-8b-instant"
)

response = agent.start("Hello! I'm your patent research and innovation assistant. "
                      "How can I help you explore patents and identify "
                      "innovation opportunities today?") 