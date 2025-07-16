from praisonaiagents import Agent

agent = Agent(
    instructions="You are a robotics and automation AI agent. "
                "Help users understand robotics, automation systems, "
                "and industrial applications. Provide guidance on "
                "robot programming, automation workflows, "
                "sensor integration, and robotic process automation.",
    llm="openrouter/moonshotai/kimi-k2"
)

response = agent.start("Hello! I'm your robotics and automation assistant. "
                      "How can I help you with robotics and "
                      "automation systems today?") 