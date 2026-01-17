from praisonaiagents import VideoAgent

agent = VideoAgent(llm="runwayml/gen4_turbo")
video = agent.generate("Animate this forest", input_reference="forest.jpg")
print(video.id)
