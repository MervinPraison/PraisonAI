from praisonaiagents import Agent

agent = Agent(
    instructions="You are a patent research and innovation AI agent. "
                "Help users conduct patent research, analyze intellectual property, "
                "identify innovation opportunities, and navigate patent filing processes. "
                "Provide guidance on patent searches, prior art analysis, "
                "innovation strategy, IP protection, and technology landscape assessment.",
    llm="groq/llama3.1-8b-instant"
)

response = agent.start("Hello! I'm your patent research and innovation assistant. "
                      "How can I help you with patent research, innovation strategy, "
                      "and intellectual property protection today?") 