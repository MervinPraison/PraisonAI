from praisonaiagents import Agent

agent = Agent(
    instructions="You are a cybersecurity AI agent. "
                "Help users understand security concepts, analyze security threats, "
                "and provide guidance on security best practices, risk assessment, "
                "and security architecture design.",
    llm="openai/gpt-4o"
)

response = agent.start("Hello! I'm your cybersecurity assistant. "
                      "How can I help you with security concepts today?") 