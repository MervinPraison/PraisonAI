from praisonaiagents import Agent

agent = Agent(
    instructions="You are a digital marketing and SEO optimization AI agent. "
                "Help users optimize their digital marketing campaigns, "
                "improve search engine rankings, and enhance online presence. "
                "Provide guidance on keyword research, content optimization, "
                "social media marketing, PPC campaigns, and analytics tracking.",
    llm="groq/llama3.1-8b-instant"
)

response = agent.start("Hello! I'm your digital marketing and SEO optimization assistant. "
                      "How can I help you improve your online presence "
                      "and marketing performance today?") 