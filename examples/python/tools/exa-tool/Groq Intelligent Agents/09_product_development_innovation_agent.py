from praisonaiagents import Agent

agent = Agent(
    instructions="You are a product development and innovation AI agent. "
                "Help users develop products from ideation to launch, "
                "conduct market validation, and create innovative solutions. "
                "Provide guidance on product strategy, user research, "
                "MVP development, feature prioritization, and go-to-market planning.",
    llm="groq/llama3.1-8b-instant"
)

response = agent.start("Hello! I'm your product development and innovation assistant. "
                      "How can I help you develop innovative products "
                      "and bring them to market successfully today?") 