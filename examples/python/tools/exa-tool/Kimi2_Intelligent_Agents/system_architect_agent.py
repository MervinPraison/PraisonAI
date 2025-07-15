from praisonaiagents import Agent

agent = Agent(
    instructions="You are a system architecture AI agent. "
                "Help users design scalable, efficient, and robust system architectures. "
                "Provide guidance on microservices, cloud infrastructure, database design, API design, and system integration patterns.",
    llm="openrouter/moonshotai/kimi-k2"
)

response = agent.start("Hello! I'm your system architecture assistant. "
                      "How can I help you design and optimize your system architecture today?") 