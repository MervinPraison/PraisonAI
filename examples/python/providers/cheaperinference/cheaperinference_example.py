"""
Basic example of using Cheaper Inference with PraisonAI.

Cheaper Inference is an OpenAI-compatible LLM gateway.
Each model costs 15–60% less than the list price of its lab.

Sign up at https://cheaperinference.com/signup
Model list: https://cheaperinference.com/#models
"""

import os

from praisonaiagents import Agent

api_key = os.getenv("CHEAPER_INFERENCE_API_KEY")
if not api_key:
    raise RuntimeError(
        "CHEAPER_INFERENCE_API_KEY is not set. Set it before running this example: "
        "export CHEAPER_INFERENCE_API_KEY=your_api_key"
    )

agent = Agent(
    instructions="You are a helpful assistant",
    llm={
        # The "openai/" prefix selects the OpenAI-compatible route.
        # Other models: "openai/gpt-5.4", "openai/claude-sonnet-5"
        "model": "openai/gpt-5.4-mini",
        "api_key": api_key,
        "base_url": "https://api.cheaperinference.com/v1",
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
