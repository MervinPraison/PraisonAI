from praisonaiagents import VideoAgent

agent = VideoAgent(llm="openai/sora-2")
video = agent.generate("A cat playing with yarn")
print(video.id)
