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

agent = Agent(
    instructions="You are a helpful assistant",
    llm="openai/moonshotai/kimi-k2.5",
    base_url="https://api.novita.ai/openai",
    api_key=os.environ.get("NOVITA_API_KEY"),
)

agent.start("Why is the sky blue?")
