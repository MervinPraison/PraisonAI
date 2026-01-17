from praisonaiagents import VideoAgent

agent = VideoAgent(llm="azure/sora-2")
video = agent.generate("Mountain landscape")
print(video.id)
