from praisonaiagents import Agent

agent = Agent(
    instructions="You are a game design AI agent. "
                 "Help users with game concept development, mechanics design, "
                 "and creative storytelling for various gaming platforms and genres.",
    llm="xai/grok-4"
)

response = agent.start(
    "I want to create a mobile puzzle game concept. "
    "Can you help me design engaging gameplay mechanics and story elements?"
) 