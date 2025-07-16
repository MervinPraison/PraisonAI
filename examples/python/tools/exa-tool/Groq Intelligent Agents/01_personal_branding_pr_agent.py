from praisonaiagents import Agent

agent = Agent(
    instructions="You are a personal branding and PR AI agent. "
                "Help users build their personal brand, manage public relations, "
                "create compelling content strategies, and enhance their online presence. "
                "Provide guidance on social media management, content creation, "
                "media relations, reputation management, and brand positioning.",
    llm="groq/llama3.1-8b-instant"
)

response = agent.start("Hello! I'm your personal branding and PR assistant. "
                      "How can I help you build your personal brand and "
                      "manage your public relations today?") 