from praisonaiagents import Agent

agent = Agent(
    instructions="You are a medical imaging AI agent. Help analyze medical images, provide preliminary assessments, and assist healthcare professionals with diagnostic support.",
    llm="xai/grok-4"
)

response = agent.start("I have an X-ray image that needs analysis. Can you help identify any abnormalities?") 