"""
Basic example of using OrcaRouter with PraisonAI

Set ORCAROUTER_API_KEY first (keys start with "sk-orca-"):
    export ORCAROUTER_API_KEY=sk-orca-...

Model ids stay namespaced the way OrcaRouter exposes them, so the id after
"orcarouter/" is itself a "vendor/model" pair. The full catalogue is at
https://www.orcarouter.ai/models
"""

from praisonaiagents import Agent

# Initialize Agent with OrcaRouter
agent = Agent(
    instructions="You are a helpful assistant",
    llm="orcarouter/openai/gpt-5.5",
)

# Example conversation
response = agent.start("Hello! Can you help me with a creative writing task?")

# Example with creative writing
writing_task = """
Write a short story about a time traveler who discovers
they can only travel to moments of great historical significance.
Make it engaging and about 200 words.
"""

response = agent.start(writing_task)

# Example with reasoning
reasoning_task = """
Explain the concept of quantum entanglement in simple terms,
and then discuss its potential applications in quantum computing.
"""

response = agent.start(reasoning_task)

# Example using the adaptive router instead of a pinned model. "orcarouter/auto"
# selects an upstream per request, so prefer a pinned model when the agent
# depends on strict structured output.
router_agent = Agent(
    instructions="You are a helpful assistant",
    llm="orcarouter/orcarouter/auto",
)

response = router_agent.start("Summarise the water cycle in three bullets.")
