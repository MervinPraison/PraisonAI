from praisonaiagents import Agent

agent = Agent(
    instructions="You are a quantum computing AI agent. "
                "Help users understand quantum computing concepts, "
                "quantum algorithms, and quantum programming. Provide guidance on "
                "quantum circuit design, quantum error correction, "
                "quantum machine learning, and quantum cryptography.",
    llm="openrouter/moonshotai/kimi-k2"
)

response = agent.start("Hello! I'm your quantum computing assistant. "
                      "How can I help you explore quantum computing "
                      "and quantum programming today?") 