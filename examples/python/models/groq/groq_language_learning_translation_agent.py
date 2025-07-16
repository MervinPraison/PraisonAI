from praisonaiagents import Agent

agent = Agent(
    instructions="You are a language learning and translation AI agent. "
                "Help users learn new languages, translate content accurately, "
                "and understand cultural nuances. Provide guidance on language learning strategies, "
                "grammar explanations, vocabulary building, pronunciation, "
                "and cultural context for effective communication.",
    llm="groq/llama3.1-8b-instant"
)

response = agent.start("Hello! I'm your language learning and translation assistant. "
                      "How can I help you learn new languages, translate content, "
                      "or understand cultural nuances today?") 