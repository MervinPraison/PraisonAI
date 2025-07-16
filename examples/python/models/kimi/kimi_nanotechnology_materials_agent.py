from praisonaiagents import Agent

agent = Agent(
    instructions="You are a nanotechnology and materials AI agent. "
                "Help users understand nanotechnology, advanced materials, "
                "and material science. Provide guidance on "
                "nanomaterials, material properties, fabrication techniques, "
                "and applications in various industries.",
    llm="openrouter/moonshotai/kimi-k2"
)

response = agent.start("Hello! I'm your nanotechnology and materials assistant. "
                      "How can I help you with nanotechnology "
                      "and materials science today?") 