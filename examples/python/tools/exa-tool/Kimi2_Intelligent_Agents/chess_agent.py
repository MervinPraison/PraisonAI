from praisonaiagents import Agent

agent = Agent(
    instructions="You are a chess AI agent. "
                "Help users improve their chess skills, analyze positions, develop strategies, and understand chess theory. "
                "Provide move analysis, opening guidance, endgame techniques, and tactical training.",
    llm="openrouter/moonshotai/kimi-k2"
)

response = agent.start("Hello! I'm your chess assistant. "
                      "How can I help you improve your chess game today?") 