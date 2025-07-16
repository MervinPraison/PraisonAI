from praisonaiagents import Agent

agent = Agent(
    instructions="You are a digital marketing and SEO optimization AI agent. "
                "Help users develop digital marketing strategies, optimize for search engines, "
                "and improve online visibility. Provide guidance on SEO best practices, "
                "content marketing, social media strategies, PPC campaigns, "
                "and analytics interpretation for better ROI.",
    llm="groq/llama3.1-8b-instant"
)

response = agent.start("Hello! I'm your digital marketing and SEO optimization assistant. "
                      "How can I help you improve your online presence, "
                      "optimize for search engines, or develop marketing strategies today?") 