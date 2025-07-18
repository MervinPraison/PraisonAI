from praisonaiagents import Agent

agent = Agent(
    instructions="You are a code review AI agent. "
                "Help developers review code for best practices, security vulnerabilities, "
                "performance issues, and maintainability. Provide constructive feedback "
                "and suggest improvements for code quality and efficiency.",
    llm="meta-llama/Llama-3.1-8B-Instruct"
)

response = agent.start("Hello! I'm your code review assistant. "
                      "How can I help you improve your code quality today?") 