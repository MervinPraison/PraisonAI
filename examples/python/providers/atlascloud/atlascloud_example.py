"""
Basic example of using Atlas Cloud with PraisonAI

Atlas Cloud (https://atlascloud.ai) is an OpenAI-compatible API gateway that
exposes 300+ models (DeepSeek, Llama, Qwen, and more) behind a single endpoint.

Because the endpoint is OpenAI-compatible, you can use it with PraisonAI by
passing an ``llm`` dict that points ``api_base`` at the Atlas Cloud endpoint.

Setup:
    export OPENAI_API_KEY=<your-atlas-cloud-key>   # e.g. apikey-xxxxxxxx
    # or pass api_key="..." directly in the llm dict below

Find available model ids at https://api.atlascloud.ai/v1/models
"""

import os

from praisonaiagents import Agent

# Initialize Agent with Atlas Cloud (OpenAI-compatible endpoint)
agent = Agent(
    instructions="You are a helpful assistant",
    llm={
        # Prefix with "openai/" so LiteLLM routes through the OpenAI-compatible path
        "model": "openai/deepseek-ai/deepseek-v4-pro",
        "api_base": "https://api.atlascloud.ai/v1",
        "api_key": os.environ.get("OPENAI_API_KEY"),  # your Atlas Cloud key
    },
)

# Example conversation
response = agent.start("Hello! Can you help me with a mathematical problem?")

# Example with mathematical reasoning
math_task = """
Solve this calculus problem step by step:
Find the derivative of f(x) = x^3 * e^(2x) using the product rule.
"""

response = agent.start(math_task)

# Example with code optimization
code_task = """
Optimize this Python function for better performance:

def find_duplicates(arr):
    duplicates = []
    for i in range(len(arr)):
        for j in range(i+1, len(arr)):
            if arr[i] == arr[j] and arr[i] not in duplicates:
                duplicates.append(arr[i])
    return duplicates
"""

response = agent.start(code_task)
