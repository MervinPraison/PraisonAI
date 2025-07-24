from praisonaiagents import Agent

agent = Agent(
    instructions="You are a research assistant AI agent. "
                "Help users conduct comprehensive research on various topics, "
                "analyze academic papers, synthesize information, and provide "
                "evidence-based insights and recommendations.",
    llm="meta-llama/Llama-3.1-8B-Instruct"
)

response = agent.start("Hello! I'm your research assistant. "
                      "How can I help you with your research project today?") 