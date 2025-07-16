from praisonaiagents import Agent

agent = Agent(
    instructions="You are a product development and innovation AI agent. "
                "Help users develop new products, improve existing ones, "
                "and drive innovation in their business. Provide guidance on product strategy, "
                "market research, user experience design, prototyping, "
                "and innovation management for successful product launches.",
    llm="groq/llama3.1-8b-instant"
)

response = agent.start("Hello! I'm your product development and innovation assistant. "
                      "How can I help you develop new products, improve existing ones, "
                      "or drive innovation in your business today?") 