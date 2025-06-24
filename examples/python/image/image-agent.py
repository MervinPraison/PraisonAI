from praisonaiagents.agent.image_agent import ImageAgent

# Create an image agent with normal mode
agent = ImageAgent(llm="dall-e-3")

# Generate an image
result = agent.chat("A cute baby sea otter playing with a laptop")
print("Image generation result:", result)