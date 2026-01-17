from praisonaiagents import ImageAgent

agent = ImageAgent(llm="openai/dall-e-3")
result = agent.generate("A sunset over mountains")
print(result.data[0].url)
