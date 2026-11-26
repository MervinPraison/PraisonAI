"""Reuse stored Responses history. Requires an OpenAI API key.

This opts into provider-side response storage. Historical tokens still count
toward the context window and input-token billing.
"""

from praisonaiagents import Agent

agent = Agent(
    instructions="Answer briefly.",
    llm={"model": "gpt-4o-mini", "server_side_conversation": True},
)
print(agent.start("My project is called ORANGE-PANDA. Remember that name."))
print(agent.start("What is my project called?"))
