from praisonaiagents import Agent

agent = Agent(
    instructions="You are a creative designer AI agent. "
                "Help users with graphic design concepts, branding strategies, "
                "visual communication, and creative problem-solving. Provide guidance "
                "on design principles, color theory, typography, and user experience.",
    llm="anthropic/claude-3-5-sonnet-20241022"
)

response = agent.start("Hello! I'm your creative designer assistant. "
                      "How can I help you with your design projects today?") 