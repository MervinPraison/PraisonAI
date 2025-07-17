from praisonaiagents import Agent

agent = Agent(
    instructions="You are a content writing AI agent. "
                "Help users create engaging blog posts, articles, marketing copy, "
                "and social media content. Provide guidance on SEO optimization, "
                "content structure, tone adjustment, and audience targeting.",
    llm="meta-llama/Llama-3.1-8B-Instruct"
)

response = agent.start("Hello! I'm your content writing assistant. "
                      "How can I help you create compelling content today?") 