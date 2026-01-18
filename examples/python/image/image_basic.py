# Image Generation with DALL-E
# Requires: export OPENAI_API_KEY=your-key

from praisonaiagents import ImageAgent

agent = ImageAgent(llm="openai/dall-e-3")
result = agent.generate("A sunset over mountains")
print(result.data[0].url)
