from praisonaiagents import VideoAgent

agent = VideoAgent(llm="openai/sora-2")

# Generate video
video = agent.generate("A sunset timelapse", seconds="8", size="1920x1080")
print(f"Started: {video.id}")

# Wait and download
completed = agent.wait_for_completion(video.id)
if completed.status == "completed":
    agent.download(video.id, "sunset.mp4")

# List all videos
videos = agent.list()

# Models: openai/sora-2, gemini/veo-3.0-generate-preview, azure/sora-2
