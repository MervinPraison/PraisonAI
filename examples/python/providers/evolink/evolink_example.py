"""
Basic example of using EvoLink.AI with PraisonAI.
"""

import os

from praisonaiagents import Agent

api_key = os.getenv("EVOLINK_API_KEY")
if not api_key:
    raise RuntimeError(
        "EVOLINK_API_KEY is not set. Set it before running this example: "
        "export EVOLINK_API_KEY=your_api_key"
    )

agent = Agent(
    instructions="You are a helpful assistant",
    llm={
        "model": "openai/gpt-5.2",
        "api_key": api_key,
        "base_url": "https://direct.evolink.ai/v1",
    },
)

response = agent.start("Hello! Share one practical AI automation idea.")
print(response)

coding_task = """
Write a Python function that validates whether a string is a palindrome.
Include a short docstring and ignore spaces and capitalization.
"""

response = agent.start(coding_task)
print(response)
