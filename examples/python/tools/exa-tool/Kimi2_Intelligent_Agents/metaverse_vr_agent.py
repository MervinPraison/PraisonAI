from praisonaiagents import Agent

agent = Agent(
    instructions="You are a metaverse and virtual reality AI agent. "
                "Help users understand metaverse concepts, VR development, "
                "and immersive technologies. Provide guidance on "
                "3D modeling, VR programming, digital twins, "
                "and virtual world design.",
    llm="openrouter/moonshotai/kimi-k2"
)

response = agent.start("Hello! I'm your metaverse and VR assistant. "
                      "How can I help you explore the metaverse "
                      "and virtual reality today?") 