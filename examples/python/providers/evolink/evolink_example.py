"""
Basic example of using EvoLink.AI with PraisonAI.
"""

import os

from praisonaiagents import Agent

agent = Agent(
    instructions="You are a helpful assistant",
    llm={
        "model": "openai/gpt-5.2",
        "api_key": os.environ["EVOLINK_API_KEY"],
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
