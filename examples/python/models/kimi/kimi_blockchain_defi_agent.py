from praisonaiagents import Agent

agent = Agent(
    instructions="You are a blockchain and DeFi AI agent. "
                "Help users understand blockchain technology, "
                "decentralized finance, and cryptocurrency. Provide guidance on "
                "smart contract development, DeFi protocols, "
                "tokenomics, and blockchain security.",
    llm="openrouter/moonshotai/kimi-k2"
)

response = agent.start("Hello! I'm your blockchain and DeFi assistant. "
                      "How can I help you explore blockchain technology "
                      "and decentralized finance today?") 