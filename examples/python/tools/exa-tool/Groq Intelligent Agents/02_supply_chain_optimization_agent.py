from praisonaiagents import Agent

agent = Agent(
    instructions="You are a supply chain optimization AI agent. "
                "Help users optimize their supply chain operations, "
                "improve logistics efficiency, and reduce costs. "
                "Provide guidance on inventory management, supplier relationships, "
                "demand forecasting, transportation optimization, and risk management.",
    llm="groq/llama3.1-8b-instant"
)

response = agent.start("Hello! I'm your supply chain optimization assistant. "
                      "How can I help you streamline your supply chain "
                      "and improve operational efficiency today?") 