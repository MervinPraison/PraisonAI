from praisonaiagents import Agent

agent = Agent(
    instructions="You are a bioinformatics and genomics AI agent. "
                "Help users understand bioinformatics, genomics, "
                "and computational biology. Provide guidance on "
                "DNA sequence analysis, protein structure prediction, "
                "genetic algorithms, and biological data mining.",
    llm="openrouter/moonshotai/kimi-k2"
)

response = agent.start("Hello! I'm your bioinformatics and genomics assistant. "
                      "How can I help you with bioinformatics "
                      "and genomics research today?") 