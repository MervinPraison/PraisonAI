from praisonaiagents import Agent

agent = Agent(
    instructions="You are a healthcare and medical research AI agent. "
                "Help users with medical research, health data analysis, "
                "and healthcare insights. Provide guidance on medical literature analysis, "
                "clinical trial research, health data interpretation, "
                "healthcare policy analysis, and patient care optimization.",
    llm="groq/llama3.1-8b-instant"
)

response = agent.start("Hello! I'm your healthcare and medical research assistant. "
                      "How can I help you with medical research "
                      "and healthcare insights today?") 