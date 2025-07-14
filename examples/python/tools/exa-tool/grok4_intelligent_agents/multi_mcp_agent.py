from praisonaiagents import Agent

agent = Agent(
    instructions="You are a multi MCP AI agent. "
                 "Help users integrate and coordinate multiple Model Context Protocol agents "
                 "for complex workflows and cross-platform automation.",
    llm="xai/grok-4"
)

response = agent.start(
    "I need to coordinate multiple tools and services for my project. "
    "Can you help me set up an integrated workflow using MCP agents?"
) 