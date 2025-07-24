"""
Basic example of using Hugging Face with PraisonAI
"""

from praisonaiagents import Agent

# Initialize Agent with Hugging Face
agent = Agent(
    instructions="You are a helpful assistant",
    llm="huggingface/meta-llama/Llama-3.1-8B-Instruct",
)

# Example conversation
response = agent.start("Hello! Can you help me with a language translation task?")

# Example with language translation
translation_task = """
Translate the following text to French and explain any cultural nuances:
"The early bird catches the worm, but the second mouse gets the cheese."
"""

response = agent.start(translation_task)

# Example with creative content generation
creative_task = """
Write a haiku about artificial intelligence and its impact on society.
Then explain the symbolism in your haiku.
"""

response = agent.start(creative_task) 