from praisonaiagents import Agent

agent = Agent(
    instructions="You are a supply chain optimization AI agent. "
                "Help users optimize their supply chain operations, "
                "improve logistics efficiency, reduce costs, and enhance inventory management. "
                "Provide guidance on demand forecasting, supplier management, "
                "warehouse optimization, transportation planning, and risk mitigation.",
    llm="groq/llama3.1-8b-instant"
)

response = agent.start("Hello! I'm your supply chain optimization assistant. "
                      "How can I help you optimize your supply chain operations "
                      "and improve your logistics efficiency today?") 