"""
Novita AI integration example for PraisonAI Agents.

Novita AI provides an OpenAI-compatible endpoint, allowing you to use
high-quality open-source models (Kimi, DeepSeek, GLM, etc.) via the
standard interface.

Prerequisites:
    Set your Novita AI API key as an environment variable:
        export NOVITA_API_KEY="your-api-key-here"

    Get your API key at: https://novita.ai
"""
import os
from praisonaiagents import Agent

api_key = os.environ.get("NOVITA_API_KEY")
if not api_key:
    raise ValueError(
        "The NOVITA_API_KEY environment variable is not set. "
        "Please set it to your Novita AI API key."
    )

agent = Agent(
    instructions="You are a helpful assistant",
    llm="openai/moonshotai/kimi-k2.5",
    base_url="https://api.novita.ai/openai",
    api_key=api_key,
)

agent.start("Why is the sky blue?")
