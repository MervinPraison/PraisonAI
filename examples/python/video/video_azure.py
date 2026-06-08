from praisonaiagents import VideoAgent
import os


if __name__ == "__main__":
    if not os.getenv("AZURE_API_BASE"):
        print("AZURE_API_BASE is not configured. Skipping Azure video example.")
    else:
        agent = VideoAgent(llm="azure/sora-2")
        video = agent.generate("Mountain landscape")
        print(video.id)
