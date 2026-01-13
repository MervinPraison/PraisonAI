from praisonaiagents import Agent

def validate_content(data):
    if len(str(data)) < 50:
        return False, "Content too short"
    return True, data

agent = Agent(
    instructions="You are a writer",
    guardrails=validate_content
)

agent.start("Write a welcome message with 5 words")