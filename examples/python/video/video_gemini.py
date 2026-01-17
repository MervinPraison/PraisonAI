from praisonaiagents import VideoAgent

agent = VideoAgent(llm="gemini/veo-3.1-generate-preview")
video = agent.generate("Ocean waves at sunset")
print(video.id)
