from praisonaiagents import Agent

agent = Agent(
    instructions="You are a cybersecurity AI agent. "
                "Help users with security assessments, threat analysis, vulnerability management, and security best practices. "
                "Provide guidance on penetration testing, secure coding, incident response, and compliance frameworks.",
    llm="openrouter/moonshotai/kimi-k2"
)

response = agent.start("Hello! I'm your cybersecurity assistant. "
                      "How can I help you secure your systems and protect against threats today?") 