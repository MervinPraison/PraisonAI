from praisonaiagents import Agent

agent = Agent(
    instructions="You are a healthcare and medical research AI agent. "
                "Help users with medical research, healthcare insights, "
                "and understanding complex medical information. Provide guidance on medical literature review, "
                "healthcare trends analysis, patient care strategies, "
                "and medical technology advancements for better healthcare outcomes.",
    llm="groq/llama3.1-8b-instant"
)

response = agent.start("Hello! I'm your healthcare and medical research assistant. "
                      "How can I help you with medical research, healthcare insights, "
                      "or understanding complex medical information today?") 