from praisonaiagents import ImageAgent

agent = ImageAgent(llm="openai/dall-e-3", style="vivid")

# Generate with options
result = agent.generate("A futuristic city", size="1792x1024", quality="hd")
print(result.data[0].url)

# Edit image (dall-e-2 only)
agent2 = ImageAgent(llm="openai/dall-e-2")
edited = agent2.edit("photo.png", "Add a rainbow")
print(edited.data[0].url)

# Generate variations
variations = agent2.variation("photo.png", n=3)
for img in variations.data:
    print(img.url)
