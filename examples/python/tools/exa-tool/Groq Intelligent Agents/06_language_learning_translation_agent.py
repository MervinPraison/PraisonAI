from praisonaiagents import Agent

agent = Agent(
    instructions="You are a language learning and translation AI agent. "
                "Help users learn new languages, translate content, "
                "and understand cultural nuances. Provide guidance on "
                "language learning strategies, grammar explanations, "
                "cultural context, and translation accuracy.",
    llm="groq/llama3.1-8b-instant"
)

response = agent.start("Hello! I'm your language learning and translation assistant. "
                      "How can I help you learn languages and translate "
                      "content effectively today?") 