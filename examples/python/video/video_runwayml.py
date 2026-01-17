from praisonaiagents import VideoAgent

agent = VideoAgent(llm="runwayml/gen4_turbo")
video = agent.generate("Animate this forest", size="1280x720", seconds="10")
print(video.id)
