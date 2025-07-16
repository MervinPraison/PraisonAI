from praisonaiagents import Agent

agent = Agent(
    instructions="You are an aerospace engineering AI agent. "
                "Help users understand aerospace engineering concepts, "
                "aircraft design, and space technology. Provide guidance on "
                "aerodynamics, propulsion systems, materials science, "
                "and satellite technology.",
    llm="openrouter/moonshotai/kimi-k2"
)

response = agent.start("Hello! I'm your aerospace engineering assistant. "
                      "How can I help you with aerospace engineering "
                      "and space technology today?") 