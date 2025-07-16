from praisonaiagents import Agent

agent = Agent(
    instructions="You are a multimodal design AI agent. "
                 "Help users with graphic design, UI/UX design, and visual content creation "
                 "by analyzing text descriptions and visual references.",
    llm="xai/grok-4"
)

response = agent.start(
    "I need to create a logo for my tech startup. "
    "Can you help me design a modern and professional logo concept?"
) 