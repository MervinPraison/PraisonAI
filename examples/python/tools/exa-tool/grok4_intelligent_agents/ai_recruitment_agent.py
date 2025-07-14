from praisonaiagents import Agent

agent = Agent(
    instructions="You are a recruitment AI agent. "
                 "Help users with candidate screening, job posting optimization, "
                 "and recruitment process automation to find the best talent.",
    llm="xai/grok-4"
)

response = agent.start(
    "I need to create a job posting for a senior software engineer position. "
    "Can you help me write an attractive and comprehensive job description?"
) 