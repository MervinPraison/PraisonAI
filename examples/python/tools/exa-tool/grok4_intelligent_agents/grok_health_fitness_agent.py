from praisonaiagents import Agent

agent = Agent(
    instructions="You are a health and fitness AI agent. Help users with workout plans, nutrition advice, wellness tips, and health monitoring guidance.",
    llm="xai/grok-4"
)

response = agent.start("I want to lose 20 pounds and build muscle. What's the best workout and nutrition plan for me?") 